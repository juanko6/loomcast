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

from .. import parada, procesos
from ..clients import comfy, llm, rife
from ..config import COLA_ESPERA_S, COLA_INTENTOS
from ..db import get_session
from ..models import ImagenLibre, Musica, Proyecto, Tema, Voz
from ..repositories import jobs as jobs_repo
from ..services import apuntes, llm_runtime, progreso
from ..services.pipeline import (
    armado,
    armado_estatico,
    casting,
    clips,
    crear_voz,
    escena_individual,
    escenas,
    i2v,
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
    "generar_resumen_episodio": series.generar_resumen_episodio,
    "generar_retrato": retratos.generar_retrato,
    "generar_retratos": retratos.generar_retratos,
    "generar_escenas": escenas.generar_escenas,
    "generar_imagenes": imagenes.generar_imagenes,
    "regenerar_imagen": imagenes.regenerar_imagen,
    "mejorar_prompt_imagen": imagen_libre.mejorar_prompt,
    "generar_previews_imagen": imagen_libre.generar_previews,
    "generar_final_imagen": imagen_libre.generar_final,
    "quitar_fondo": quitar_fondo.quitar_fondo,
    "mejorar_prompt_musica": musica.mejorar_prompt,
    "generar_musica": musica.generar,
    "generar_musica_proyecto": musica_proyecto.generar_musica_proyecto,
    "generar_portada_musica": musica.generar_portada,
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
    "mejorar_prompt_musica",
    "generar_musica_proyecto",
    "generar_resumen_episodio",
}

# Etapas que se disparan solas al terminar la anterior:
#  - voz → subtítulos (sin revisión intermedia)
#  - Ken Burns: upscale → clips → armado
#  - i2v: i2v → armado
#  - música: pista generada → portada
#    (la música del proyecto no está aquí: su job encola `generar_musica` él
#     mismo, porque la cadena conserva el ref_id y ahí cambia de proyecto a
#     pista)
# Las escenas NO encadenan a imágenes: los prompts se revisan/editan primero.
CADENA = {
    "generar_voz": "generar_subtitulos",
    "generar_upscale": "generar_clips",
    "generar_clips": "armar_video",
    "generar_i2v": "armar_video",
    # La portada se hace DESPUÉS de la pista, no tras la sugerencia del LLM:
    # así solo la tienen las pistas que existen de verdad, y cada regeneración
    # estrena portada.
    "generar_musica": "generar_portada_musica",
    "generar_clips_mixto": "armar_video",
}

# Los dos armados. Al terminar cualquiera de ellos, un episodio de serie que
# todavía no tenga resumen se cierra solo (ver `_encadenado`).
ARMADOS = ("armar_video", "armar_estatico")

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
    """Qué job sale solo tras este, si sale alguno.

    Casi todo está en `CADENA`, que es fijo por tipo. El resumen del episodio no
    puede estarlo: depende de si ese proyecto es un episodio y de si ya lo tiene
    escrito. Se encadena al armado porque es cuando el episodio está de verdad
    cerrado, y así el siguiente nace con continuidad sin que nadie se acuerde de
    pedirla. Un proyecto suelto nunca entra aquí.
    """
    if tipo in CADENA:
        return CADENA[tipo]
    if tipo in ARMADOS and series.resumen_pendiente(ref_id):
        return "generar_resumen_episodio"
    return None


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
    Voz: ["crear_voz", "clonar_voz"],
    Musica: ["mejorar_prompt_musica", "generar_musica", "generar_portada_musica"],
    ImagenLibre: ["mejorar_prompt_imagen", "generar_previews_imagen",
                  "generar_final_imagen", "quitar_fondo"],
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


def _ejecutar(tipo: str, ref_id: int, params: dict) -> str:
    """Un intento del handler, con el llama-server donde toque."""
    if tipo in JOBS_LLM:
        with llm_runtime.en_uso():
            return HANDLERS[tipo](ref_id, **params)
    llm_runtime.liberar(f"empieza {tipo}")
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
    try:
        estado, log = _intentar(job_id, tipo, ref_id, params)
        # Se lee antes de limpiar: el handler puede haber terminado bien justo
        # antes del corte, y entonces su trabajo vale pero la cadena no sigue.
        parado = parada.pedida()
        # Lo que midieron las capas de debajo (la memoria que soltó ComfyUI
        # antes de cargar el LLM, por ejemplo): el handler no lo sabe y el
        # historial de la UI es donde se lee.
        notas = apuntes.recoger()
    finally:
        progreso.limpiar()
        parada.limpiar()
        apuntes.limpiar()
    if notas:
        log = "\n\n".join(filter(None, [log, "\n".join(notas)]))
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
