from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Job

ACTIVOS = ["pendiente", "corriendo"]


def crear(s: Session, tipo: str, ref_id: int, params: str = "{}") -> Job:
    job = Job(tipo=tipo, ref_id=ref_id, params=params)
    s.add(job)
    return job


def obtener(s: Session, job_id: int) -> Job | None:
    return s.get(Job, job_id)


def activos(s: Session) -> list[Job]:
    return s.query(Job).filter(Job.estado.in_(ACTIVOS)).order_by(Job.id).all()


def activos_de_proyecto(s: Session, pid: int, tipos: list[str]) -> int:
    return (
        s.query(Job)
        .filter(Job.ref_id == pid, Job.tipo.in_(tipos), Job.estado.in_(ACTIVOS))
        .count()
    )


def tipo_activo_de_proyecto(s: Session, pid: int, tipos: list[str]) -> str | None:
    """Tipo del job en curso/pendiente del proyecto (para mostrar la etapa)."""
    job = (
        s.query(Job)
        .filter(Job.ref_id == pid, Job.tipo.in_(tipos), Job.estado.in_(ACTIVOS))
        .order_by(Job.id)
        .first()
    )
    return job.tipo if job else None


def escenas_en_cola(s: Session, pid: int) -> dict[int, str]:
    """Escenas del proyecto con una regeneración pendiente o en curso, mapeadas
    a lo que se está rehaciendo ('imagen' o 'clip'). Permite que la UI las marque
    en vez de bloquear los botones mientras la cola trabaja."""
    import json

    out = {}
    jobs = (
        s.query(Job)
        .filter(Job.ref_id == pid,
                Job.tipo.in_(["regenerar_imagen", "regenerar_clip"]),
                Job.estado.in_(ACTIVOS))
        .order_by(Job.id)
        .all()
    )
    for j in jobs:
        orden = json.loads(j.params or "{}").get("orden")
        if orden is not None:
            out[orden] = "imagen" if j.tipo == "regenerar_imagen" else "clip"
    return out


def marcar_corriendo(s: Session, job: Job) -> None:
    job.estado = "corriendo"


def finalizar(s: Session, job: Job, estado: str, log: str) -> None:
    job.estado = estado
    job.log = log
    job.finished_at = datetime.now(timezone.utc)
