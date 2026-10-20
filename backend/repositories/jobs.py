from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Job

ACTIVOS = ["pendiente", "corriendo"]
# Los que ya no se van a mover: lo que ve el historial de la cabecera.
TERMINADOS = ["ok", "error", "cancelado"]


def crear(s: Session, tipo: str, ref_id: int, params: str = "{}",
          prioridad: int = 0) -> Job:
    job = Job(tipo=tipo, ref_id=ref_id, params=params, prioridad=prioridad)
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


def activos_de_voz(s: Session, voz_id: int) -> int:
    return (
        s.query(Job)
        .filter(Job.ref_id == voz_id,
                Job.tipo.in_(["crear_voz", "clonar_voz"]),
                Job.estado.in_(ACTIVOS))
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


def termino_ok(s: Session, ref_id: int, tipo: str) -> bool:
    """Si esa etapa ya se completó alguna vez sobre ese proyecto.

    Hace falta para las etapas cuyo resultado puede ser legítimamente vacío: un
    reparto sin personajes es la respuesta normal en *curiosidades*, así que no
    hay nada en disco ni en la base que distinga "el casting no se ha hecho" de
    "se hizo y no hay nadie". El job terminado sí lo distingue.
    """
    return (
        s.query(Job)
        .filter(Job.ref_id == ref_id, Job.tipo == tipo, Job.estado == "ok")
        .first()
        is not None
    )


def activos_de_proyecto_ids(s: Session, pid: int, tipos: list[str]) -> list[int]:
    """Ids de los jobs del proyecto que están en la cola o corriendo. Es lo que
    hay que cancelar para parar el autopiloto de un proyecto concreto."""
    return [
        j.id
        for j in s.query(Job)
        .filter(Job.ref_id == pid, Job.tipo.in_(tipos), Job.estado.in_(ACTIVOS))
        .order_by(Job.id)
        .all()
    ]


def corriendo(s: Session) -> Job | None:
    """El job que el worker tiene entre manos. La cola es de un solo hilo, así
    que como mucho hay uno."""
    return s.query(Job).filter(Job.estado == "corriendo").order_by(Job.id).first()


def pendientes(s: Session) -> list[Job]:
    return s.query(Job).filter(Job.estado == "pendiente").order_by(Job.id).all()


def historial(s: Session, limite: int = 20) -> list[Job]:
    """Los últimos jobs terminados, del más reciente al más viejo."""
    return (
        s.query(Job)
        .filter(Job.estado.in_(TERMINADOS))
        .order_by(Job.id.desc())
        .limit(limite)
        .all()
    )


def marcar_corriendo(s: Session, job: Job, intento: int = 1) -> None:
    job.estado = "corriendo"
    job.intentos = intento


def finalizar(s: Session, job: Job, estado: str, log: str) -> None:
    job.estado = estado
    job.log = log
    job.finished_at = datetime.now(timezone.utc)


def cancelar(s: Session, job: Job, motivo: str) -> None:
    """Marca el job como cancelado.

    Se usa igual para uno que esperaba su turno (el worker lo salta cuando le
    llega) y para el que está corriendo (a quien además hay que cortarle el
    trabajo; ver services/cancelacion.py). El estado es propio y no "error":
    pararlo fue una decisión, no un fallo, y en el historial se lee distinto.
    """
    finalizar(s, job, "cancelado", motivo)
