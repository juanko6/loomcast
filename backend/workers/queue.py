"""Cola de jobs en un hilo: las etapas LLM/GPU corren una a la vez.

El orden no es el de llegada, es el de **prioridad y luego llegada**: lo que se
pide a mano adelanta a lo que encola un autopiloto. Con un lote de diez vídeos
produciéndose, rehacer una imagen del proyecto que estás mirando tardaba lo que
quedara del lote, o sea media tarde, y eso convertía la cola en una lista de
espera. La prioridad va dentro del elemento de la cola y también en la columna
del job, para que `recuperar_pendientes()` restituya el orden tras un reinicio.

Nada de esto toca los reintentos ni la parada: un job reintenta **dentro de su
turno** (no se re-encola, así que no pierde el sitio), y quien para sigue
vaciando la cola entera sin mirar prioridades.
"""
import json
import queue as _queue
import threading
import time
import traceback

import httpx

from .. import memoria, parada, procesos
from ..clients import comfy, llm, rife
from ..config import (
    COLA_ESPERA_S,
    COLA_INTENTOS,
    COLA_MEMORIA_MODELO_GB,
    I2V_MEMORIA_GB,
    IMAGEN_MEMORIA_GB,
    MUSICA_MEMORIA_GB,
)
from ..db import get_session
from ..models import (
    Album,
    ImagenLibre,
    MiembroReparto,
    Musica,
    Proyecto,
    Serie,
    Tema,
    Voz,
)
from ..repositories import jobs as jobs_repo
from ..services import apuntes, llm_runtime, progreso
from ..services.pipeline import (
    album,
    armado,
    armado_estatico,
    casting,
    clips,
    crear_voz,
    escena_individual,
    escenas,
    i2v,
    imagen_animada,
    imagen_libre,
    imagenes,
    musica,
    musica_proyecto,
    quitar_fondo,
    retratos,
    series,
    subtitulos,
    texto,
    upscale,
    voz,
)

HANDLERS = {
    "generar_ideas": texto.generar_ideas,
    "generar_guion": texto.generar_guion,
    "generar_metadatos": texto.generar_metadatos,
    "crear_voz": crear_voz.crear_voz,
    "clonar_voz": crear_voz.clonar_voz,
    "generar_voz": voz.generar_voz,
    "generar_subtitulos": subtitulos.generar_subtitulos,
    "generar_casting": casting.generar_casting,
    "generar_hilo": series.generar_hilo,
    "generar_resumen_episodio": series.generar_resumen_episodio,
    "generar_retrato": retratos.generar_retrato,
    "generar_retratos": retratos.generar_retratos,
    "generar_retrato_reparto": retratos.generar_retrato_reparto,
    "generar_escenas": escenas.generar_escenas,
    "generar_imagenes": imagenes.generar_imagenes,
    "regenerar_imagen": imagenes.regenerar_imagen,
    "mejorar_prompt_imagen": imagen_libre.mejorar_prompt,
    "generar_previews_imagen": imagen_libre.generar_previews,
    "generar_final_imagen": imagen_libre.generar_final,
    "quitar_fondo": quitar_fondo.quitar_fondo,
    "mejorar_movimiento_animada": imagen_animada.mejorar_movimiento,
    "animar_imagen": imagen_animada.animar,
    "escalar_animada": imagen_animada.escalar,
    "mejorar_prompt_musica": musica.mejorar_prompt,
    "generar_musica": musica.generar,
    "generar_musica_proyecto": musica_proyecto.generar_musica_proyecto,
    "sintetizar_musica_proyecto": musica_proyecto.sintetizar_musica_proyecto,
    "generar_portada_musica": musica.generar_portada,
    "planificar_album": album.planificar_album,
    "escribir_album": album.escribir_album,
    "escribir_pista_album": album.escribir_pista_album,
    "generar_portada_album": album.generar_portada_album,
    "regenerar_clip": escena_individual.regenerar_clip,
    "generar_clips_mixto": escena_individual.generar_clips_mixto,
    "generar_upscale": upscale.generar_upscale,
    "generar_clips": clips.generar_clips,
    "generar_i2v": i2v.generar_i2v,
    "armar_video": armado.armar_video,
    "armar_estatico": armado_estatico.armar_estatico,
}

# Etapas que hablan con el llama-server. El resto (Qwen3-TTS, whisper, ComfyUI,
# ffmpeg) pelea por la misma memoria unificada, así que antes de cualquiera de
# ellas se descarga el LLM y así no compiten por la RAM.
JOBS_LLM = {
    "generar_ideas",
    "generar_guion",
    "generar_metadatos",
    "generar_casting",
    "generar_escenas",
    "mejorar_prompt_imagen",
    "mejorar_movimiento_animada",
    "mejorar_prompt_musica",
    "generar_musica_proyecto",
    "planificar_album",
    "escribir_album",
    "escribir_pista_album",
    "generar_hilo",
    "generar_resumen_episodio",
}

# GiB libres que se esperan a ver antes de dejar que un job cargue su modelo.
#
# Todo el que carga algo grande pasa por aquí, porque el `/free` con el que la
# etapa anterior soltó al terminar es **a ciegas**: vuelve en 1 ms con los pesos
# todavía dentro, y con --gpu-only la descarga llega ~1,7 s después, bajando
# primero la memoria libre. `_hacer_sitio` espera a medirla de verdad.
#
# Empezó cubriendo solo los modelos que viven DENTRO del backend (Qwen3-TTS,
# whisper), que era la mitad que faltaba del error ya arreglado por el lado del
# LLM. Los que viven dentro de ComfyUI se quedaron fuera porque su inquilino
# mayor era Z-Image, 11,5 GiB, y colaba. ACE-Step 1.5 son 18,5 GiB y dejó de
# colar: el 2026-11-05, una pista de 300 s cargó sobre un llama-server de 22 GiB
# que el kernel no había terminado de reclamar, y su portada cargó Z-Image
# encima de la pista todavía dentro de ComfyUI — 15 GiB al swap.
#
# Lo que no está aquí no carga nada que pese: ffmpeg (armado, clips), RIFE, el
# ESRGAN del upscale (0,06 GiB), el u2net de quitar fondo (0,18) y el motion,
# que se dibuja con Pillow.
MEMORIA_JOB: dict[str, float] = {
    # Dentro del backend: 8 sobra para el TTS en fp16 (3,4 de pesos, pico
    # medido de 4,2) y no llega a bloquear nunca.
    "generar_voz": COLA_MEMORIA_MODELO_GB,
    "crear_voz": COLA_MEMORIA_MODELO_GB,
    "clonar_voz": COLA_MEMORIA_MODELO_GB,
    "generar_subtitulos": COLA_MEMORIA_MODELO_GB,
    # Dentro de ComfyUI: ACE-Step 1.5, el más grande de todos.
    "generar_musica": MUSICA_MEMORIA_GB,
    "sintetizar_musica_proyecto": MUSICA_MEMORIA_GB,
    # Dentro de ComfyUI: los motores de imagen. La portada de la pista está
    # aquí porque es justo la que llega encadenada detrás de la música.
    "generar_portada_musica": IMAGEN_MEMORIA_GB,
    "generar_portada_album": IMAGEN_MEMORIA_GB,
    "generar_imagenes": IMAGEN_MEMORIA_GB,
    "regenerar_imagen": IMAGEN_MEMORIA_GB,
    "generar_previews_imagen": IMAGEN_MEMORIA_GB,
    "generar_final_imagen": IMAGEN_MEMORIA_GB,
    "generar_retrato": IMAGEN_MEMORIA_GB,
    "generar_retratos": IMAGEN_MEMORIA_GB,
    "generar_retrato_reparto": IMAGEN_MEMORIA_GB,
    # Dentro de ComfyUI: los motores i2v. El mixto puede llevar escenas i2v.
    "generar_i2v": I2V_MEMORIA_GB,
    "generar_clips_mixto": I2V_MEMORIA_GB,
    # La imagen animada carga el mismo LTX-2.5. El escalado puede no cargar
    # nada (realesrgan-ncnn va por fuera de ComfyUI), pero corre detrás de
    # animar y quiere a LTX fuera antes de llenar la memoria de cuadros 4K.
    "animar_imagen": I2V_MEMORIA_GB,
    "escalar_animada": I2V_MEMORIA_GB,
}

# Etapas que se disparan solas al terminar la anterior:
#  - voz → subtítulos (sin revisión intermedia)
#  - Ken Burns: upscale → clips → armado
#  - i2v: i2v → armado
#  - música del proyecto: brief → síntesis (los dos llevan el id del proyecto,
#    así que la cadena vale; son dos jobs y no uno porque el brief habla con el
#    LLM y la síntesis con ComfyUI, y entre job y job la cola descarga el
#    llama-server — los dos modelos no caben juntos)
#  - música de la biblioteca: pista generada → portada
#    (la portada de la música del proyecto no está aquí: la encola su síntesis,
#     porque ahí el ref_id cambia de proyecto a pista)
# Las escenas NO encadenan a imágenes: los prompts se revisan/editan primero.
CADENA = {
    "generar_voz": "generar_subtitulos",
    "generar_musica_proyecto": "sintetizar_musica_proyecto",
    "generar_upscale": "generar_clips",
    "generar_clips": "armar_video",
    "generar_i2v": "armar_video",
    # La portada se hace DESPUÉS de la pista, no tras la sugerencia del LLM:
    # así solo la tienen las pistas que existen de verdad, y cada regeneración
    # estrena portada.
    "generar_musica": "generar_portada_musica",
    # Álbum: el plan y los briefs van seguidos, los dos con el LLM cargado. La
    # síntesis no se encadena: antes el usuario revisa el álbum y lo lanza.
    "planificar_album": "escribir_album",
    "generar_clips_mixto": "armar_video",
}

# Modo de video → job con el que arranca. El estático es un solo job; el de
# movimiento (Ken Burns) es una cadena upscale → clips → armado, y los demás los
# resuelve `CADENA` igual. Vive aquí, al lado de la cadena, porque es lo mismo
# que ella: qué job hace qué. Lo leen el paso de vídeo (a mano) y el autopiloto.
MODOS_VIDEO = {
    "estatico": "armar_estatico",
    "kenburns": "generar_upscale",
    "i2v": "generar_i2v",
    # Respeta el modo elegido en cada escena: el video puede mezclarlos.
    "mixto": "generar_clips_mixto",
}


def _encadenado(tipo: str, ref_id: int) -> str | None:
    """Qué job sale solo tras este, si sale alguno. Todo está en `CADENA`.

    El resumen del episodio **estuvo aquí**, encadenado al armado, y de ahí se
    fue: el resumen solo depende del guion, así que esperar al vídeo metía el
    render en el camino de la historia. Peor, lo hacía mal — un lote con la
    parada de revisión del guion puesta libera la línea y mete el episodio
    siguiente, que escribía su guion sin el resumen del anterior porque el
    anterior ni se había armado—. Ahora lo pide el autopiloto en cuanto el guion
    está aprobado (`autopiloto._que_falta`), que es cuando la historia está de
    verdad cerrada. Encadenarlo aquí no valdría: la cadena se come el
    `tras_etapa` del guion, o sea la propia parada de revisión.
    """
    # Una pista de álbum no estrena portada: la del disco se hace una vez al
    # final (cargar el motor de imagen entre pista y pista es pagar la carga de
    # ACE-Step otra vez en cada vuelta).
    if tipo == "generar_musica" and _es_de_album(ref_id):
        return None
    return CADENA.get(tipo)


def _es_de_album(musica_id: int) -> bool:
    with get_session() as s:
        m = s.get(Musica, musica_id)
        return m is not None and m.album_id is not None


# Intentos y espera de los reintentos ([cola] de config.toml). Se copian a
# variables del módulo para que los tests puedan apretarlas sin esperar de
# verdad los 20 s.
INTENTOS = COLA_INTENTOS
ESPERA_BASE_S = COLA_ESPERA_S

# Fallos que merecen otro intento: los de las fronteras del sistema, donde lo
# normal es que algo de fuera no estuviera listo todavía.
#
#  - ComfyError (clients/comfy.py): ComfyUI rechaza el workflow, no responde o
#    se pasa del tope. El caso típico: está arrancando, o cargando modelos.
#  - LLMError (clients/llm.py): el llama-server responde un código de error o
#    devuelve algo que no es el JSON pedido. Lo segundo pasa de verdad, y otro
#    intento sale distinto porque la generación no es determinista.
#  - RifeError (clients/rife.py) y ProcesoTimeout (procesos.py): un proceso
#    externo que se cuelga y se corta por tiempo.
#  - httpx.HTTPError y OSError: la red local y el disco (el llama-server en
#    medio de un reinicio, ComfyUI cerrando la conexión).
#
# Quedan fuera a propósito:
#  - ValueError, que es lo que lanzan las validaciones de las etapas ("Faltan
#    clips de las escenas...", "No hay escenas", "La mezcla de música está
#    activada pero el proyecto no tiene pista..."). Falta una entrada: repetir
#    da el mismo error un rato más tarde.
#  - El RuntimeError pelado de un ffmpeg que sale con código distinto de cero
#    (pipeline/clips.py, armado): ahí ffmpeg corrió y dijo que no podía con lo
#    que se le dio.
#  - Todo lo demás (AttributeError, KeyError…), que es un bug nuestro: repetirlo
#    solo tarda tres veces más en enseñarlo.
TRANSITORIOS = (
    comfy.ComfyError,
    llm.LLMError,
    rife.RifeError,
    procesos.ProcesoTimeout,
    httpx.HTTPError,
    OSError,
)

# Las que caen dentro de TRANSITORIOS por herencia pero son justo lo contrario:
# un FileNotFoundError es un OSError, y un archivo que no está (o un binario de
# ffmpeg que no está instalado) no aparece por repetir tres veces.
NO_TRANSITORIOS = (FileNotFoundError, PermissionError)

# A qué apunta el `ref_id` de cada tipo de job. Sirve para no reintentar un job
# cuyo proyecto o pista se borró mientras fallaba: el segundo intento daría otro
# error, y el que cuenta es el primero. Lo que no esté aquí trabaja sobre un
# proyecto.
_REF_POR_MODELO = {
    Tema: ["generar_ideas"],
    Serie: ["generar_hilo"],
    MiembroReparto: ["generar_retrato_reparto"],
    Voz: ["crear_voz", "clonar_voz"],
    Musica: ["mejorar_prompt_musica", "generar_musica", "generar_portada_musica",
             "escribir_pista_album"],
    Album: ["planificar_album", "escribir_album", "generar_portada_album"],
    ImagenLibre: ["mejorar_prompt_imagen", "generar_previews_imagen",
                  "generar_final_imagen", "quitar_fondo",
                  "mejorar_movimiento_animada", "animar_imagen", "escalar_animada"],
}
REF_MODELO = {tipo: modelo for modelo, tipos in _REF_POR_MODELO.items() for tipo in tipos}

# Orden de la cola. Lo que pide una persona va primero porque está delante de
# la pantalla esperándolo; lo que encola un autopiloto puede esperar, que para
# eso es automático. Son números y no un booleano para poder meter algo en medio
# el día que haga falta sin volver a tocar a todos los que encolan.
PRIORIDAD_MANUAL = 0
PRIORIDAD_AUTOPILOTO = 10

# La cola ordena por (prioridad, job_id). El id sirve de desempate y da el orden
# de llegada gratis: lo pone la base y crece siempre, así que dentro de una
# prioridad sigue siendo una FIFO, y un lote conserva su orden interno.
_cola: "_queue.PriorityQueue[tuple[int, int]]" = _queue.PriorityQueue()


def encolar(tipo: str, ref_id: int, *, prioridad: int = PRIORIDAD_MANUAL,
            **params) -> int:
    """Encola un job. Los `params` extra se guardan en JSON y llegan al handler
    como kwargs: sirven para jobs que actúan sobre una escena concreta.

    `prioridad` es de palabra clave a propósito: así no puede colarse por error
    como un kwarg del handler, que es lo que son todos los demás.
    """
    if tipo not in HANDLERS:
        raise ValueError(f"Tipo de job desconocido: {tipo}")
    with get_session() as s:
        job = jobs_repo.crear(s, tipo, ref_id, json.dumps(params), prioridad)
        s.commit()
        job_id = job.id
    _cola.put((prioridad, job_id))
    return job_id


def _tomar() -> int:
    """El siguiente job de la cola: el de más prioridad y, a igualdad, el que
    llegó antes. Espera si no hay ninguno."""
    return _cola.get()[1]


def _hacer_sitio(tipo: str, gb: float) -> None:
    """Espera a tener `gb` libres antes de dejar que el job cargue su modelo.

    No lanza nunca, al contrario que su gemelo de `llm_runtime`: allí lo que
    venía detrás eran 22 GiB y arrancarlos a ciegas mataba al backend con
    `Killed: 9`, así que negarse era lo correcto. Aquí la etapa tiene que correr
    igual —negarle la pista al usuario porque el equipo esté ocupado sería
    peor—; lo que hace falta es no cargar encima de algo que está a punto de
    irse al swap, y dejar dicho cuánta memoria había si pasa.

    Quién pasa por aquí y con cuánto, en `MEMORIA_JOB`.
    """
    lib = comfy.liberar_memoria(hasta_gb=gb)
    linea = f"Memoria para {tipo} ({gb:.0f} GiB): {lib}"
    print(f"[cola] {linea}", flush=True)
    apuntes.anotar(linea)


# Por debajo de esto no se anota: el sistema pagina un poco por su cuenta y un
# historial que avise de 80 MiB en cada job no se lee.
SWAP_AVISO_GB = 0.5


def _anotar_swap(tipo: str, antes: float | None) -> None:
    """Deja dicho en el historial del job si su etapa mandó memoria al swap.

    Es el dato que no se ve de ninguna otra forma: al terminar la etapa, la
    memoria disponible vuelve a parecer sana y el único rastro de que el equipo
    ha estado paginando cuatro minutos es este contador. Sin esto, la única
    manera de enterarse era tener `btop` abierto en el momento justo.

    Mide `Swapouts`, no `Pageouts` (ver `backend/memoria.py`), y nunca lanza:
    esto corre con el job ya terminado y no puede estropearlo.
    """
    if antes is None:
        return
    despues = memoria.swapouts_gb()
    if despues is None or despues - antes < SWAP_AVISO_GB:
        return
    linea = (
        f"{tipo} mandó {despues - antes:.1f} GiB al swap mientras corría: lo "
        "que cargó no cabía. Si la medición de memoria de arriba dice que al "
        "empezar había sitio de sobra, entonces no fue un solapamiento con la "
        "etapa anterior sino el pico de esta, y el sitio donde mirar es lo que "
        "carga su propio workflow"
    )
    print(f"[cola] {linea}", flush=True)
    apuntes.anotar(linea)


def _ejecutar(tipo: str, ref_id: int, params: dict) -> str:
    """Un intento del handler, con el llama-server donde toque."""
    if tipo in JOBS_LLM:
        with llm_runtime.en_uso():
            return HANDLERS[tipo](ref_id, **params)
    llm_runtime.liberar(f"empieza {tipo}")
    gb = MEMORIA_JOB.get(tipo)
    if gb:
        _hacer_sitio(tipo, gb)
    return HANDLERS[tipo](ref_id, **params)


def _ref_viva(tipo: str, ref_id: int) -> bool:
    """Si lo que el job genera (proyecto, pista, imagen, voz, tema) sigue ahí."""
    with get_session() as s:
        return s.get(REF_MODELO.get(tipo, Proyecto), ref_id) is not None


def _esperar(segundos: float) -> bool:
    """Espera antes de reintentar. False si entretanto se pidió parar.

    Se duerme a trocitos y no de un tirón: quien pulsa "parar" durante la espera
    no tiene por qué aguantar los 40 s que le quedaban.
    """
    fin = time.monotonic() + segundos
    while True:
        if parada.pedida():
            return False
        resto = fin - time.monotonic()
        if resto <= 0:
            return True
        time.sleep(min(0.25, resto))


def _log_fallo(fallo: str, intento: int) -> str:
    if intento == 1:
        return fallo
    return f"Falló {intento} veces; el último error:\n{fallo}"


def _intentar(job_id: int, tipo: str, ref_id: int, params: dict) -> tuple[str, str]:
    """Ejecuta el handler reintentando lo transitorio. Devuelve (estado, log).

    Los reintentos se hacen aquí, dentro del turno del job, y no re-encolándolo:
    así conserva su fila (y su cuenta de intentos), no se cuela por detrás de lo
    que estuviera esperando, y la etapa encadenada —que mira el estado final—
    sigue saliendo una sola vez, tras el intento bueno.
    """
    intento = 0
    while True:
        intento += 1
        with get_session() as s:
            jobs_repo.marcar_corriendo(s, jobs_repo.obtener(s, job_id), intento)
            s.commit()
        try:
            return "ok", _ejecutar(tipo, ref_id, params)
        except parada.Parado as e:
            # El corte limpio: un bucle por lotes entre elementos, el LLM entre
            # trozos, Whisper entre segmentos o un proceso al que matamos.
            return "cancelado", str(e)
        except Exception as e:
            fallo = traceback.format_exc(limit=5)
            if parada.pedida():
                # El error es consecuencia del corte (el workflow interrumpido
                # en ComfyUI, el ffmpeg al que mandamos SIGTERM): es una parada,
                # no un fallo.
                return "cancelado", f"Parado a petición del usuario:\n{fallo}"
            transitorio = (isinstance(e, TRANSITORIOS)
                           and not isinstance(e, NO_TRANSITORIOS))
            if not transitorio or intento >= max(1, INTENTOS):
                return "error", _log_fallo(fallo, intento)
            if not _ref_viva(tipo, ref_id):
                return "error", (
                    f"{_log_fallo(fallo, intento)}\n"
                    "No se reintenta: lo que este job generaba ya no existe."
                )
            # Crece con el intento: lo que falla suele estar arrancando o
            # recuperándose, y volver enseguida lo encuentra igual.
            if not _esperar(ESPERA_BASE_S * 2 ** (intento - 1)):
                return "cancelado", f"Parado esperando para reintentar:\n{fallo}"


def _procesar(job_id: int) -> None:
    # El autopiloto se importa aquí dentro: el worker le pregunta qué toca ahora
    # y él encola, así que a nivel de módulo el ciclo sería real. La dirección
    # buena es la del playbook (servicio → cola); esta es la de vuelta.
    from ..services import autopiloto

    with get_session() as s:
        job = jobs_repo.obtener(s, job_id)
        if job is None:
            return
        tipo, ref_id, prioridad = job.tipo, job.ref_id, job.prioridad
        # Cancelado mientras esperaba su turno: se salta tal cual. Su estado y
        # su log ya los escribió quien lo canceló. Lo que sí hace falta es
        # decírselo al autopiloto: si era su etapa, se quedaría "corriendo" sin
        # nada en la cola, o sea colgado para siempre.
        if job.estado == "cancelado":
            autopiloto.tras_corte(ref_id, tipo, "cancelado", job.log)
            return
        params = json.loads(job.params or "{}")
    parada.iniciar(job_id)
    progreso.iniciar(job_id, tipo)
    apuntes.iniciar()
    swap = memoria.swapouts_gb()
    try:
        estado, log = _intentar(job_id, tipo, ref_id, params)
        # Se lee antes de limpiar: el handler puede haber terminado bien justo
        # antes del corte, y entonces su trabajo vale pero la cadena no sigue.
        parado = parada.pedida()
        _anotar_swap(tipo, swap)
        # Lo que midieron las capas de debajo (la memoria que soltó ComfyUI
        # antes de cargar el LLM, por ejemplo): el handler no lo sabe y el
        # historial de la UI es donde se lee.
        notas = apuntes.recoger()
    finally:
        progreso.limpiar()
        parada.limpiar()
        apuntes.limpiar()
    if notas:
        # En un fallo las notas van DELANTE del error, no detrás: son el
        # contexto del fallo (cuánta memoria había, qué soltó ComfyUI) y el
        # error tiene que quedar al final, que es de donde el autopiloto saca
        # el motivo que escribe (`autopiloto._resumen`). Con las notas al final
        # el motivo de una etapa caída era la medición de memoria.
        partes = [log, "\n".join(notas)]
        if estado == "error":
            partes.reverse()
        log = "\n\n".join(filter(None, partes))
    if estado == "ok" and parado:
        # Pasa en las etapas que no se pueden cortar a mitad (la síntesis de voz
        # es una sola llamada a PyTorch): se pidió parar, la etapa terminó de
        # todos modos y su trabajo vale. Queda dicho en el log para que el
        # historial no haga pensar que la parada no llegó.
        log = (
            f"{log}\n\nSe pidió parar cuando esta etapa ya estaba en marcha y no se "
            "podía cortar a mitad: terminó, pero no se encadena la siguiente."
        )
    with get_session() as s:
        jobs_repo.finalizar(s, jobs_repo.obtener(s, job_id), estado, log)
        s.commit()
    # Las regeneraciones de una sola escena no encadenan: rearmar el video
    # entero en cada retoque costaría más que el propio retoque. Un job parado
    # tampoco: la etapa siguiente trabajaría sobre material a medias, y si se
    # paró es justo lo que no se quería.
    #
    # El autopiloto se mueve justo aquí, en el hilo del worker y después de que
    # el job esté finalizado en la base: es el único sitio desde el que encola.
    # Las etapas no lo hacen por su cuenta a propósito (ver models/autopiloto),
    # porque entonces parar no pararía nada.
    if estado == "ok" and not parado:
        siguiente = _encadenado(tipo, ref_id)
        if siguiente:
            # La cadena hereda la prioridad: una tirada del autopiloto no debe
            # adelantar a lo que se pida a mano por el hecho de ir encadenada, y
            # un upscale pedido a mano no debe perder su sitio al llegar a los
            # clips.
            encolar(siguiente, ref_id, prioridad=prioridad)
            return
        autopiloto.tras_etapa(ref_id, tipo)
        return
    # Falló, se canceló o terminó justo cuando se pidió parar: en los tres casos
    # su autopiloto se detiene y deja la línea libre para el proyecto siguiente
    # del lote. Que un vídeo salga mal no puede tirar los otros nueve.
    autopiloto.tras_corte(ref_id, tipo, estado, log)


def _loop() -> None:
    while True:
        _procesar(_tomar())


def arrancar_worker() -> None:
    threading.Thread(target=_loop, daemon=True, name="loomcast-worker").start()


def recuperar_pendientes() -> None:
    """Re-encola jobs que quedaron a medias si el server se reinició."""
    with get_session() as s:
        pendientes = jobs_repo.activos(s)
        for j in pendientes:
            j.estado = "pendiente"
        s.commit()
    for j in pendientes:
        _cola.put((j.prioridad, j.id))
