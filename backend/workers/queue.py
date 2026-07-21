"""Cola de jobs en un hilo: las etapas LLM/GPU corren una a la vez."""
import queue as _queue
import threading
import traceback

from ..db import get_session
from ..repositories import jobs as jobs_repo
from ..services.pipeline import (
    armado,
    clips,
    crear_voz,
    escenas,
    imagenes,
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
    "generar_voz": voz.generar_voz,
    "generar_subtitulos": subtitulos.generar_subtitulos,
    "generar_escenas": escenas.generar_escenas,
    "generar_imagenes": imagenes.generar_imagenes,
    "generar_upscale": upscale.generar_upscale,
    "generar_clips": clips.generar_clips,
    "armar_video": armado.armar_video,
}

# Etapas que se disparan solas al terminar la anterior:
#  - voz → subtítulos (sin revisión intermedia)
#  - el video con movimiento es una cadena: upscale → clips → armado
# Las escenas NO encadenan a imágenes: los prompts se revisan/editan primero.
CADENA = {
    "generar_voz": "generar_subtitulos",
    "generar_upscale": "generar_clips",
    "generar_clips": "armar_video",
}

_cola: "_queue.Queue[int]" = _queue.Queue()


def encolar(tipo: str, ref_id: int) -> int:
    if tipo not in HANDLERS:
        raise ValueError(f"Tipo de job desconocido: {tipo}")
    with get_session() as s:
        job = jobs_repo.crear(s, tipo, ref_id)
        s.commit()
        job_id = job.id
    _cola.put(job_id)
    return job_id


def _procesar(job_id: int) -> None:
    with get_session() as s:
        job = jobs_repo.obtener(s, job_id)
        jobs_repo.marcar_corriendo(s, job)
        s.commit()
        tipo, ref_id = job.tipo, job.ref_id
    try:
        estado, log = "ok", HANDLERS[tipo](ref_id)
    except Exception:
        estado, log = "error", traceback.format_exc(limit=5)
    with get_session() as s:
        jobs_repo.finalizar(s, jobs_repo.obtener(s, job_id), estado, log)
        s.commit()
    if estado == "ok" and tipo in CADENA:
        encolar(CADENA[tipo], ref_id)


def _loop() -> None:
    while True:
        _procesar(_cola.get())


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
        _cola.put(j.id)
