"""Worker de jobs en un hilo: las etapas LLM/GPU corren una a la vez."""
import queue
import threading
import traceback
from datetime import datetime, timezone

from .db import get_session
from .models import Job
from .stages import subtitulos, texto, voz

HANDLERS = {
    "generar_ideas": texto.generar_ideas,
    "generar_guion": texto.generar_guion,
    "generar_metadatos": texto.generar_metadatos,
    "generar_voz": voz.generar_voz,
    "generar_subtitulos": subtitulos.generar_subtitulos,
}

# Etapas que se disparan solas al terminar la anterior (sin punto de revisión)
CADENA = {"generar_voz": "generar_subtitulos"}

_cola: "queue.Queue[int]" = queue.Queue()


def encolar(tipo: str, ref_id: int) -> int:
    if tipo not in HANDLERS:
        raise ValueError(f"Tipo de job desconocido: {tipo}")
    with get_session() as s:
        job = Job(tipo=tipo, ref_id=ref_id)
        s.add(job)
        s.commit()
        job_id = job.id
    _cola.put(job_id)
    return job_id


def _procesar(job_id: int) -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        job.estado = "corriendo"
        s.commit()
        tipo, ref_id = job.tipo, job.ref_id
    try:
        resultado = HANDLERS[tipo](ref_id)
        estado, log = "ok", resultado
    except Exception:
        estado, log = "error", traceback.format_exc(limit=5)
    with get_session() as s:
        job = s.get(Job, job_id)
        job.estado = estado
        job.log = log
        job.finished_at = datetime.now(timezone.utc)
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
        pendientes = (
            s.query(Job).filter(Job.estado.in_(["pendiente", "corriendo"])).all()
        )
        for j in pendientes:
            j.estado = "pendiente"
        s.commit()
    for j in pendientes:
        _cola.put(j.id)
