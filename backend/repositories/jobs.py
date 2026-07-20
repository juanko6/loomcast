from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Job

ACTIVOS = ["pendiente", "corriendo"]


def crear(s: Session, tipo: str, ref_id: int) -> Job:
    job = Job(tipo=tipo, ref_id=ref_id)
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


def marcar_corriendo(s: Session, job: Job) -> None:
    job.estado = "corriendo"


def finalizar(s: Session, job: Job, estado: str, log: str) -> None:
    job.estado = estado
    job.log = log
    job.finished_at = datetime.now(timezone.utc)
