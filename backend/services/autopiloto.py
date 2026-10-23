"""Autopiloto y lotes: de un tema a varios final.mp4 sin conducir cada paso.

Hasta aquí Loomcast se conducía a mano: cada etapa es un botón del stepper, y
entre botón y botón hay una persona mirando. Eso es lo que quieres mientras
afinas una plantilla y lo que no quieres cuando ya sabes lo que sale: diez
vídeos son ciento diez clics.

Cómo funciona, y por qué así:

  - **El autopiloto es estado, no un job largo.** Vive en la tabla
    `autopilotos` y lo mueve el worker: al terminar bien una etapa le pregunta
    `tras_etapa()` qué falta, y aquí se encola la siguiente. Hacerlo al revés
    —una etapa que encola la siguiente desde dentro— es lo que convertiría la
    parada en caliente en algo que no para: la parada corta el job que corre y
    vacía la cola, y el autopiloto volvería a llenarla. Aquí el único que
    encola es el worker, solo tras una etapa que terminó bien y solo si no se
    pidió parar.
  - **No hay una escalera fija de etapas.** Se pregunta qué le falta al
    proyecto (`_que_falta`), que es lo mismo que mira el stepper de la UI. Así
    un autopiloto lanzado sobre un proyecto a medias arranca donde esté y no
    rehace lo que ya hay, y una etapa que no deja rastro no puede dejar la
    tirada dando vueltas: si lo que falta sigue siendo lo que acaba de
    terminar, se detiene y lo dice.
  - **Las paradas de revisión se respetan por defecto.** Son las tres que ya
    tiene el flujo de hoy (idea, guion, prompts de escena), y están ahí porque
    corregir en ellas es barato y el error se propaga caro: media hora de GPU
    sobre un guion malo. Quien quiera producción sin manos las desactiva al
    lanzar, o las quita de `[autopiloto].paradas` en config.toml.
  - **El lote es secuencial.** La cola es de un solo hilo a propósito (las
    etapas se pelean por la misma memoria unificada), así que los proyectos de
    un lote se producen de uno en uno: cuando el que corría deja la línea
    —acabó, falló o se paró en una revisión— entra el siguiente.
  - **Un fallo detiene su proyecto y nada más.** Que un vídeo salga mal no
    puede tirar los otros nueve, así que el autopiloto que falla se cierra con
    el motivo escrito y la línea sigue.

La música entra en la escalera como una etapa más (`[autopiloto] musica` en
config.toml la quita): la banda sonora se escribe desde esta historia, así que
en automático no hay a quién preguntarle si la quiere, y una pista que no suena
en su vídeo sería media etapa — por eso, cuando la hace el autopiloto, además
enciende la mezcla.

Lo que el autopiloto **no** hace: rehacer una imagen o un clip que no convenza,
ni elegir la voz (se elige al lanzar, como el modo de vídeo). Y las etapas que
encola pasan por la cola de siempre, o sea por la descarga del LLM antes de
cualquier etapa de GPU y por la espera real de memoria de `llm_runtime`: no hay
atajo, y es el mismo camino que recorre un clic.
"""
from ..config import AUTOPILOTO_MUSICA, AUTOPILOTO_PARADAS, PROYECTOS_DIR
from ..db import get_session
from ..models import PARADA_TRAS, PARADAS
from ..repositories import autopilotos as autopilotos_repo
from ..repositories import escenas as escenas_repo
from ..repositories import guiones as guiones_repo
from ..repositories import ideas as ideas_repo
from ..repositories import jobs as jobs_repo
from ..repositories import metadatos as metadatos_repo
from ..repositories import musica as musica_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import temas as temas_repo
from ..workers import queue
from .pipeline import musica as musica_pipeline
from .pipeline import retratos
from .pipeline import series as series_pipeline
from .pipeline.imagenes import ruta_imagen

# Etapas que el autopiloto conduce. Lo que no esté aquí le es ajeno y no lo
# mueve: regenerar una imagen a mano mientras espera una revisión no debe
# hacerle creer que la revisión está atendida.
ETAPAS = {
    "generar_guion",
    "generar_metadatos",
    "generar_voz",
    "generar_subtitulos",
    "generar_casting",
    "generar_retratos",
    "generar_escenas",
    "generar_imagenes",
    "generar_musica_proyecto",
    "sintetizar_musica_proyecto",
    "generar_resumen_episodio",
    *queue.MODOS_VIDEO.values(),
    # Los eslabones intermedios de las cadenas de montaje: el autopiloto encola
    # el primero (según el modo) y la cola encadena el resto, pero si uno de
    # ellos falla es su tirada la que se tiene que detener.
    "generar_clips",
    "armar_video",
}

# Lo que se lee en la UI cuando se para en una revisión. Dice qué mirar, porque
# "esperando" a secas no dice dónde hay que ir.
MOTIVO_PARADA = {
    "guion": "Esperando que revises el guion",
    "escenas": "Esperando que revises los prompts de escena",
}

MOTIVO_HECHO = "El vídeo está montado"

# Cuántas etapas puede encolar una tirada antes de que se dé por perdida. La
# escalera completa son una docena; el margen deja sitio a las que se repiten
# por una regeneración pedida a mano y aun así corta un bucle en seguida.
TOPE_ETAPAS = 40


class ProyectoNoExiste(LookupError):
    pass


class TemaNoExiste(LookupError):
    pass


class LoteNoExiste(LookupError):
    pass


class YaEnMarcha(RuntimeError):
    """Ese proyecto ya tiene un autopiloto vivo."""


class NoEstaEsperando(RuntimeError):
    """No hay ninguna revisión pendiente que continuar."""


class SinVoz(ValueError):
    """Hace falta la narración y el proyecto no tiene voz elegida."""


class ModoVideoInvalido(ValueError):
    pass


class ParadaInvalida(ValueError):
    pass


class SinIdeas(ValueError):
    """El tema no tiene ninguna idea que producir."""


# --- qué le falta al proyecto -----------------------------------------------

def _que_falta(s, p, modo_video: str) -> str | None:
    """La etapa que toca ahora en ese proyecto, o None si ya está montado.

    Se mira de lo más avanzado a lo más atrás a propósito. Al revés, un proyecto
    que llegó a las escenas sin haber pasado por el reparto (porque el reparto
    vacío es legítimo y no siempre se pide) volvería a hacer el casting, y eso
    invalidaría los prompts ya escritos: el reparto se pega literal en ellos.
    """
    base = PROYECTOS_DIR / p.slug
    if (base / "final.mp4").exists():
        return None

    escenas = escenas_repo.por_proyecto(s, p.id)
    if escenas:
        if all(ruta_imagen(p.slug, e.orden).exists() for e in escenas):
            return _falta_musica(s, p) or queue.MODOS_VIDEO[modo_video]
        return "generar_imagenes"

    # Sin escenas todavía. Las escenas se segmentan sobre `palabras.json`, que
    # es lo que deja Whisper, así que hasta tenerlo no hay nada que proponer.
    if not (base / "palabras.json").exists():
        if guiones_repo.ultimo(s, p.id) is None:
            return "generar_guion"
        # El canon del episodio va **aquí**, pegado al guion, y no al final del
        # montaje: la historia queda cerrada cuando está escrita, y el episodio
        # siguiente lo necesita para poder escribirse ya. Con la parada de
        # revisión del guion puesta, esto es lo primero que se hace al aprobarlo
        # —que es justo lo que significa "canon": lo que el usuario dio por
        # bueno—. Un vídeo suelto nunca entra aquí.
        if series_pipeline.falta_resumen(s, p):
            return "generar_resumen_episodio"
        # El reparto va **antes** de la voz, no después. Con el formato de
        # líneas el guion ya dice quién habla, y cada uno dice las suyas con su
        # propia voz, que se escribe desde su ficha: fijarlo después dejaba el
        # episodio entero narrado por una sola voz, la del narrador, porque al
        # narrar todavía no había nadie en el reparto.
        if not jobs_repo.termino_ok(s, p.id, "generar_casting"):
            return "generar_casting"
        if metadatos_repo.ultimo(s, p.id) is None:
            return "generar_metadatos"
        if not (base / "voz.mp3").exists():
            return "generar_voz"
        return "generar_subtitulos"

    # Un reparto vacío es la respuesta normal en *curiosidades*, así que no hay
    # nada en disco que distinga "no se ha hecho el casting" de "se hizo y no
    # sale nadie": lo distingue su job terminado. Lo normal es que ya esté
    # hecho de antes de narrar; esto recoge los proyectos que pasaron por la
    # voz cuando el casting todavía iba detrás.
    if not jobs_repo.termino_ok(s, p.id, "generar_casting"):
        return "generar_casting"
    if retratos.pendientes(s, p.id):
        return "generar_retratos"
    return "generar_escenas"


def _falta_musica(s, p) -> str | None:
    """Qué le falta a la banda sonora de este proyecto, si es que le falta algo.

    Son dos etapas porque son dos modelos que no caben juntos: el brief lo
    escribe el LLM y la pista la sintetiza ComfyUI. Lo que las distingue es lo
    que dejaron: la fila de `musicas` que apunta el proyecto, y su audio.

    Va justo antes del montaje y no antes: la pista se escribe desde el guion y
    los planos, y dura lo que dura la narración, así que todo eso ya está. Y si
    alguien eligió a mano una pista de la biblioteca, esto no toca nada: ya hay
    música.
    """
    if not AUTOPILOTO_MUSICA:
        return None
    if p.musica_id is None or musica_repo.obtener(s, p.musica_id) is None:
        return "generar_musica_proyecto"
    if musica_pipeline.ruta_audio(p.musica_id) is None:
        return "sintetizar_musica_proyecto"
    return None


def _mezclar_su_musica(s, p) -> None:
    """Enciende la mezcla de la pista que el autopiloto acaba de hacer.

    A mano la mezcla es un interruptor aparte a propósito: la pista también
    vale suelta, sin voz, para redes. En automático no hay nadie que lo pulse,
    y una banda sonora escrita para esta historia que no suena en su vídeo sería
    media etapa.

    Se enciende aquí, con el audio ya en disco, y no al encolar la música:
    `armar_video` falla a propósito si la mezcla está puesta y la pista no
    existe, y una tirada parada a mitad dejaría el proyecto en esa trampa.
    """
    if p.musica_id is not None and musica_pipeline.ruta_audio(p.musica_id):
        p.musica_mezclar = True


def _params(etapa: str, auto) -> dict:
    """Los kwargs con los que se encola cada etapa.

    Son los mismos que manda la UI al pulsarla: el modo de clonado de la voz y
    el motor i2v del modo elegido. El resto de las etapas no llevan ninguno.
    """
    if etapa == "generar_voz":
        return {"modo": "clon"}
    if auto.motor and etapa in ("generar_i2v", "generar_clips_mixto"):
        return {"motor": auto.motor}
    return {}


def _encolar(auto, etapa: str) -> int:
    return queue.encolar(
        etapa, auto.proyecto_id, prioridad=queue.PRIORIDAD_AUTOPILOTO,
        **_params(etapa, auto),
    )


# --- lanzar -----------------------------------------------------------------

def _elegir_voz(pid: int, voz: str) -> None:
    """Fija la voz del proyecto antes de arrancar.

    El import va aquí dentro: `services/proyectos` lee el estado del autopiloto
    para el detalle del proyecto, así que a nivel de módulo el ciclo sería real.
    """
    from . import proyectos as proyectos_service

    proyectos_service.seleccionar_voz(pid, voz)


def _validar(modo_video: str, paradas: list[str]) -> None:
    if modo_video not in queue.MODOS_VIDEO:
        raise ModoVideoInvalido(modo_video)
    desconocidas = [p for p in paradas if p not in PARADAS]
    if desconocidas:
        raise ParadaInvalida(", ".join(desconocidas))


def _paradas(paradas: list[str] | None) -> list[str]:
    """Las paradas pedidas, o las de config.toml si no se dijo nada.

    `None` es "las de siempre" y `[]` es "ninguna, producción sin manos": son
    dos cosas distintas y la API tiene que poder decir las dos.
    """
    return list(AUTOPILOTO_PARADAS if paradas is None else paradas)


def arrancar(pid: int, modo_video: str = "kenburns", motor: str = "",
             voz: str = "", paradas: list[str] | None = None,
             lote_id: int | None = None) -> dict:
    """Pone un proyecto en automático desde donde esté hasta su final.mp4.

    El modo de montaje se elige aquí igual que se elige en el paso de vídeo: es
    la misma decisión y no tiene un valor obvio. La voz también, porque sin ella
    la narración no se puede generar y es lo primero que se encontraría.
    """
    paradas = _paradas(paradas)
    _validar(modo_video, paradas)
    if voz:
        _elegir_voz(pid, voz)

    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if autopilotos_repo.vivo_de_proyecto(s, pid) is not None:
            raise YaEnMarcha(pid)
        falta = _que_falta(s, p, modo_video)
        # La narración se clona de una voz del banco, así que sin voz elegida la
        # etapa fallaría dos minutos más tarde. Vale más decirlo al lanzar.
        antes_de_narrar = ("generar_guion", "generar_casting",
                           "generar_metadatos", "generar_voz")
        if falta in antes_de_narrar and not p.voz:
            raise SinVoz(pid)
        auto = autopilotos_repo.crear(
            s, pid, modo_video, motor, paradas, lote_id,
            estado="pendiente" if lote_id else "corriendo",
        )
        s.flush()
        if falta is None:
            autopilotos_repo.marcar(s, auto, "hecho", MOTIVO_HECHO)
        datos = a_dict(auto)
        s.commit()
        auto_id, estado = auto.id, auto.estado

    # Un autopiloto de lote no arranca aquí: entra en la línea cuando le toque
    # (ver `_entrar_el_siguiente`). Uno suelto empieza ya.
    if estado == "corriendo":
        _siguiente_etapa(auto_id, falta)
    return datos


def _siguiente_etapa(auto_id: int, etapa: str | None) -> None:
    """Encola `etapa`, o cierra la tirada si ya no falta nada."""
    if etapa is None:
        _cerrar(auto_id, "hecho", MOTIVO_HECHO)
        return
    with get_session() as s:
        auto = autopilotos_repo.obtener(s, auto_id)
        if auto is None or auto.estado != "corriendo":
            return
        pasado_de_vueltas = auto.encoladas >= TOPE_ETAPAS
        # Esa etapa ya está en la cola o corriendo: lo normal es haber aprobado
        # la idea (que encola el guion) y lanzar el autopiloto acto seguido.
        # Encolarla otra vez gastaría una pasada entera del LLM para pisar lo
        # mismo, así que se engancha a la que ya va: cuando termine, el worker
        # vendrá a preguntar qué toca y la tirada sigue desde ahí.
        ya_en_marcha = jobs_repo.activos_de_proyecto(s, auto.proyecto_id, [etapa]) > 0
        if not pasado_de_vueltas:
            auto.encoladas += 1
            auto.etapa = etapa
            s.commit()
    if pasado_de_vueltas:
        _cerrar(
            auto_id, "error",
            f"El autopiloto lleva {TOPE_ETAPAS} etapas sin llegar al vídeo y se "
            f"detiene aquí: algo no avanza (iba a repetir «{etapa}»). Mira el "
            "historial de la cola.",
        )
        return
    if ya_en_marcha:
        return
    _encolar(auto, etapa)


# --- lo que mueve el worker -------------------------------------------------

def tras_etapa(pid: int, tipo: str) -> None:
    """Una etapa terminó bien: encola la siguiente, para en una revisión o cierra.

    La llama el worker con el job ya finalizado en la base. Solo mueve a un
    autopiloto que esté `corriendo`: uno que espera una revisión sigue
    esperando aunque entretanto se pida una etapa a mano, porque la revisión es
    de una persona y no la atiende un botón cualquiera.
    """
    if tipo not in ETAPAS:
        return
    with get_session() as s:
        auto = autopilotos_repo.vivo_de_proyecto(s, pid)
        if auto is None or auto.estado != "corriendo":
            return
        auto.etapa = tipo
        auto_id, lote_id = auto.id, auto.lote_id
        parada = PARADA_TRAS.get(tipo)
        toca_revisar = bool(parada) and parada in auto.paradas_activas
        if toca_revisar:
            autopilotos_repo.marcar(s, auto, "esperando", MOTIVO_PARADA[parada])
        s.commit()
        p = proyectos_repo.obtener(s, pid)
        if p is not None and tipo == "sintetizar_musica_proyecto":
            _mezclar_su_musica(s, p)
            s.commit()
        falta = None if p is None else _que_falta(s, p, auto.modo_video)

    if toca_revisar:
        # Parar a revisar libera la línea: si no, un lote con las paradas
        # puestas se quedaría clavado en el primer guion y los otros nueve no
        # empezarían nunca. La máquina sigue trabajando mientras revisas.
        _entrar_el_siguiente(lote_id)
        return
    if p is None:
        return
    if falta == tipo:
        # La etapa dijo que terminó bien y el proyecto sigue necesitándola: sin
        # este freno la tirada la repetiría para siempre.
        _cerrar(
            auto_id, "error",
            f"«{tipo}» terminó sin dejar lo que hacía falta, así que el "
            "autopiloto no puede avanzar. Mira el log de ese trabajo.",
        )
        return
    _siguiente_etapa(auto_id, falta)


def tras_corte(pid: int, tipo: str, estado: str, log: str) -> None:
    """Una etapa falló, se canceló o terminó justo cuando se pidió parar.

    En los tres casos la tirada se detiene: si fue un fallo queda en `error` con
    el motivo, y si se paró queda en `parado`. La línea del lote sigue con el
    proyecto siguiente, porque un vídeo que sale mal no puede tirar los otros.
    """
    if tipo not in ETAPAS:
        return
    with get_session() as s:
        auto = autopilotos_repo.vivo_de_proyecto(s, pid)
        # Solo se detiene al que estaba produciendo. Si esperaba una revisión o
        # su turno en el lote, el job que acaba de romperse no era suyo —será
        # una regeneración pedida a mano— y matar la tirada por eso sería un
        # efecto que nadie pidió.
        if auto is None or auto.estado != "corriendo":
            return
        auto_id = auto.id
    if estado == "error":
        _cerrar(auto_id, "error", f"Falló «{tipo}»: {_resumen(log)}")
    else:
        _cerrar(auto_id, "parado", f"Se paró en «{tipo}»")


def _resumen(log: str) -> str:
    """La última línea con contenido del log, que es donde está el error."""
    lineas = [x.strip() for x in (log or "").splitlines() if x.strip()]
    return lineas[-1][:200] if lineas else "sin detalle"


def _cerrar(auto_id: int, estado: str, motivo: str) -> None:
    with get_session() as s:
        auto = autopilotos_repo.obtener(s, auto_id)
        if auto is None:
            return
        autopilotos_repo.marcar(s, auto, estado, motivo)
        s.commit()
        lote_id = auto.lote_id
    _entrar_el_siguiente(lote_id)


# --- continuar tras una revisión --------------------------------------------

def continuar(pid: int) -> dict:
    """Sigue desde la parada de revisión en la que estaba esperando.

    Es el "visto, adelante" de la persona, y por eso es un botón y no un
    temporizador: la parada existe justo para que alguien mire.
    """
    with get_session() as s:
        if proyectos_repo.obtener(s, pid) is None:
            raise ProyectoNoExiste(pid)
        auto = autopilotos_repo.vivo_de_proyecto(s, pid)
        if auto is None or auto.estado != "esperando":
            raise NoEstaEsperando(pid)
        # Vuelve a la línea por la puerta del lote: si otro proyecto del mismo
        # lote está produciendo, este espera su turno en vez de competir por la
        # GPU con él.
        hermano_corriendo = auto.lote_id is not None and any(
            a.estado == "corriendo" for a in autopilotos_repo.de_lote(s, auto.lote_id)
        )
        autopilotos_repo.marcar(
            s, auto, "pendiente" if hermano_corriendo else "corriendo",
            "Esperando turno en el lote" if hermano_corriendo else "",
        )
        s.commit()
        auto_id, estado, datos = auto.id, auto.estado, a_dict(auto)

    if estado == "corriendo":
        _arrancar_etapa_pendiente(auto_id)
    return datos


def _arrancar_etapa_pendiente(auto_id: int) -> None:
    """Pregunta qué falta y lo encola. Se usa al continuar y al entrar en la
    línea: en los dos casos el proyecto puede haberse movido a mano entretanto,
    así que la etapa no se recuerda, se vuelve a calcular."""
    with get_session() as s:
        auto = autopilotos_repo.obtener(s, auto_id)
        if auto is None or auto.estado != "corriendo":
            return
        p = proyectos_repo.obtener(s, auto.proyecto_id)
        if p is None:
            return
        falta = _que_falta(s, p, auto.modo_video)
    _siguiente_etapa(auto_id, falta)


# --- parar ------------------------------------------------------------------

def detener(pid: int, motivo: str = "Parado desde la interfaz") -> dict:
    """Apaga el autopiloto de un proyecto y corta lo que tuviera en la cola.

    Cancelar sus jobs es parte de pararlo: dejar el flag apagado con una etapa
    todavía en la cola sería un autopiloto que "no está" y aun así termina un
    vídeo.
    """
    with get_session() as s:
        if proyectos_repo.obtener(s, pid) is None:
            raise ProyectoNoExiste(pid)
        auto = autopilotos_repo.vivo_de_proyecto(s, pid)
        if auto is None:
            return {"parado": False}
        autopilotos_repo.marcar(s, auto, "parado", motivo)
        s.commit()
        lote_id = auto.lote_id
        ids = jobs_repo.activos_de_proyecto_ids(s, pid, sorted(ETAPAS))

    _cancelar(ids)
    _entrar_el_siguiente(lote_id)
    return {"parado": True, "jobs_cancelados": len(ids)}


def _cancelar(ids: list[int]) -> None:
    """Cancela esos jobs por la vía de siempre (`services/jobs`), que es la que
    además corta en caliente el que esté corriendo."""
    from . import jobs as jobs_service

    for job_id in ids:
        jobs_service.cancelar(job_id)


def parar_todos(motivo: str) -> int:
    """Apaga **todos** los autopilotos vivos. La llama la parada de la interfaz.

    Es lo primero que hace parar, antes de cancelar los jobs: así, cuando el
    worker termine de cortar la etapa en curso y venga a preguntar qué toca
    ahora, se encuentre con que ya no hay autopiloto al que seguir. Si el orden
    fuera el contrario, entre lo uno y lo otro cabría que arrancara el proyecto
    siguiente del lote justo después de haberlo parado todo.

    No cancela jobs: de eso se encarga quien la llama, que es el mismo que para
    la cola. Los que esperaban revisión también se apagan: el botón dice "parar"
    y tiene que parar, y relanzar un autopiloto es un clic que retoma el
    proyecto donde esté.
    """
    with get_session() as s:
        vivos = autopilotos_repo.vivos(s)
        for auto in vivos:
            autopilotos_repo.marcar(s, auto, "parado", motivo)
        s.commit()
        return len(vivos)


# --- lotes ------------------------------------------------------------------

def _entrar_el_siguiente(lote_id: int | None) -> None:
    """Mete en la línea al próximo proyecto del lote, si queda alguno.

    La línea es de uno: la cola tiene un solo hilo porque las etapas se pelean
    por la memoria unificada, así que paralelizar un lote solo cambiaría de
    sitio el cuello de botella y además metería dos modelos grandes a la vez,
    que es justo lo que mata al backend.
    """
    if lote_id is None:
        return
    with get_session() as s:
        if any(a.estado == "corriendo" for a in autopilotos_repo.de_lote(s, lote_id)):
            return
        siguiente = autopilotos_repo.siguiente_del_lote(s, lote_id)
        if siguiente is None:
            return
        autopilotos_repo.marcar(s, siguiente, "corriendo", "")
        s.commit()
        auto_id = siguiente.id
    _arrancar_etapa_pendiente(auto_id)


def lanzar_lote(tema_id: int, modo_video: str = "kenburns", motor: str = "",
                voz: str = "", paradas: list[str] | None = None) -> dict:
    """Varias ideas de un tema → un proyecto por idea, en producción seguida.

    Aquí es donde cuenta la parada de **idea**: con ella puesta (lo normal) solo
    se producen las ideas que alguien aprobó a mano, que es exactamente la
    revisión que el flujo de hoy ya hace. Sin ella entran también las
    propuestas, y entonces el lote es "tema → vídeos" sin tocar nada; las
    descartadas no entran nunca, porque descartarlas ya fue una decisión.
    """
    paradas = _paradas(paradas)
    _validar(modo_video, paradas)

    with get_session() as s:
        if temas_repo.obtener(s, tema_id) is None:
            raise TemaNoExiste(tema_id)
        admitidos = ("aprobada",) if "idea" in paradas else ("aprobada", "propuesta")
        ideas = [i.id for i in ideas_repo.por_tema(s, tema_id)
                 if i.estado in admitidos]
        if not ideas:
            raise SinIdeas(tema_id)
        lote = autopilotos_repo.crear_lote(s, tema_id)
        s.commit()
        lote_id = lote.id

    # Un proyecto por idea, sin encolar su guion: de encolar se encarga el
    # autopiloto cuando le toque, y si lo hiciera `crear_proyecto` los diez
    # guiones saldrían de golpe y el lote dejaría de ser secuencial.
    from . import ideas as ideas_service

    arrancados = []
    for idea_id in ideas:
        pid = ideas_service.crear_proyecto(idea_id, encolar_guion=False)["proyecto_id"]
        with get_session() as s:
            # Un proyecto que ya venía con un autopiloto vivo (porque se lanzó
            # suelto antes) no se mete en el lote: tiene su propia tirada.
            if autopilotos_repo.vivo_de_proyecto(s, pid) is not None:
                continue
        arrancados.append(
            arrancar(pid, modo_video, motor, voz, paradas, lote_id=lote_id)
        )

    _entrar_el_siguiente(lote_id)
    return ver_lote(lote_id)


# --- lo que lee la interfaz -------------------------------------------------

def a_dict(auto) -> dict:
    """Lo que la API expone de un autopiloto. Recibe la fila y no un id porque
    quien lo pinta (el detalle del proyecto) ya la tiene en su sesión."""
    parada = PARADA_TRAS.get(auto.etapa or "")
    return {
        "id": auto.id,
        "proyecto_id": auto.proyecto_id,
        "lote_id": auto.lote_id,
        "estado": auto.estado,
        "modo_video": auto.modo_video,
        "motor": auto.motor,
        "paradas": auto.paradas_activas,
        "etapa": auto.etapa,
        "motivo": auto.motivo,
        # En qué parada espera, para que la UI lleve al sitio donde se revisa.
        # Vacío si no está esperando a nadie.
        "parada": parada if auto.estado == "esperando" and parada else "",
    }


def ver_lote(lote_id: int) -> dict:
    with get_session() as s:
        lote = autopilotos_repo.obtener_lote(s, lote_id)
        if lote is None:
            raise LoteNoExiste(lote_id)
        tema = temas_repo.obtener(s, lote.tema_id)
        autos = autopilotos_repo.de_lote(s, lote.id)
        return _lote_dict(s, lote, tema, autos)


def _lote_dict(s, lote, tema, autos) -> dict:
    por_estado = {}
    for a in autos:
        por_estado[a.estado] = por_estado.get(a.estado, 0) + 1
    corriendo = next((a for a in autos if a.estado == "corriendo"), None)
    actual = None
    if corriendo is not None:
        p = proyectos_repo.obtener(s, corriendo.proyecto_id)
        idea = ideas_repo.obtener(s, p.idea_id) if p else None
        actual = {
            "proyecto_id": corriendo.proyecto_id,
            "titulo": idea.titulo if idea else (p.slug if p else ""),
            "etapa": corriendo.etapa,
            # Cuántos van antes que él, para leer "proyecto 3 de 10".
            "posicion": [a.id for a in autos].index(corriendo.id) + 1,
        }
    return {
        "id": lote.id,
        "tema_id": lote.tema_id,
        "tema": tema.texto if tema else "",
        "total": len(autos),
        "pendientes": por_estado.get("pendiente", 0),
        "esperando": por_estado.get("esperando", 0),
        "hechos": por_estado.get("hecho", 0),
        "errores": por_estado.get("error", 0),
        "parados": por_estado.get("parado", 0),
        "actual": actual,
        "proyectos": [
            {
                "proyecto_id": a.proyecto_id,
                "estado": a.estado,
                "etapa": a.etapa,
                "motivo": a.motivo,
            }
            for a in autos
        ],
    }


def listar_lotes(limite: int = 10) -> list[dict]:
    """Los lotes, del más reciente al más antiguo. Es lo que alimenta el panel
    de la cola: en qué proyecto va, en qué etapa y cuántos quedan."""
    with get_session() as s:
        out = []
        for lote in autopilotos_repo.lotes(s)[:limite]:
            tema = temas_repo.obtener(s, lote.tema_id)
            out.append(
                _lote_dict(s, lote, tema, autopilotos_repo.de_lote(s, lote.id))
            )
        return out
