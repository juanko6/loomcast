from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Autopiloto, Lote
from ..models.autopiloto import TERMINADOS, VIVOS


def crear(s: Session, proyecto_id: int, modo_video: str, motor: str,
          paradas: list[str], lote_id: int | None = None,
          estado: str = "corriendo") -> Autopiloto:
    a = Autopiloto(
        proyecto_id=proyecto_id, lote_id=lote_id, estado=estado,
        modo_video=modo_video, motor=motor, paradas=",".join(paradas),
    )
    s.add(a)
    return a


def obtener(s: Session, autopiloto_id: int) -> Autopiloto | None:
    return s.get(Autopiloto, autopiloto_id)


def vivo_de_proyecto(s: Session, proyecto_id: int) -> Autopiloto | None:
    """El autopiloto en marcha de un proyecto, si tiene alguno.

    Como mucho hay uno: lanzarlo dos veces sobre el mismo proyecto es lo que el
    servicio rechaza. Los terminados se quedan en la tabla porque son el
    historial de por qué se paró aquella tirada.
    """
    return (
        s.query(Autopiloto)
        .filter(Autopiloto.proyecto_id == proyecto_id,
                Autopiloto.estado.in_(VIVOS))
        .order_by(Autopiloto.id.desc())
        .first()
    )


def ultimo_de_proyecto(s: Session, proyecto_id: int) -> Autopiloto | None:
    """El último, vivo o no: es lo que la UI enseña para contar cómo acabó."""
    return (
        s.query(Autopiloto)
        .filter(Autopiloto.proyecto_id == proyecto_id)
        .order_by(Autopiloto.id.desc())
        .first()
    )


def vivos(s: Session) -> list[Autopiloto]:
    return (
        s.query(Autopiloto)
        .filter(Autopiloto.estado.in_(VIVOS))
        .order_by(Autopiloto.id)
        .all()
    )


def de_lote(s: Session, lote_id: int) -> list[Autopiloto]:
    """Los del lote en el orden en que se lanzaron, que es el de producción."""
    return (
        s.query(Autopiloto)
        .filter(Autopiloto.lote_id == lote_id)
        .order_by(Autopiloto.id)
        .all()
    )


def siguiente_del_lote(s: Session, lote_id: int) -> Autopiloto | None:
    """El próximo que entra en la línea: el primero que espera turno."""
    return (
        s.query(Autopiloto)
        .filter(Autopiloto.lote_id == lote_id, Autopiloto.estado == "pendiente")
        .order_by(Autopiloto.id)
        .first()
    )


def marcar(s: Session, a: Autopiloto, estado: str, motivo: str = "",
           etapa: str | None = None) -> None:
    a.estado = estado
    a.motivo = motivo
    if etapa is not None:
        a.etapa = etapa
    a.finished_at = datetime.now(timezone.utc) if estado in TERMINADOS else None


def borrar_de_proyecto(s: Session, proyecto_id: int) -> None:
    s.query(Autopiloto).filter(Autopiloto.proyecto_id == proyecto_id).delete()


# --- lotes ------------------------------------------------------------------

def crear_lote(s: Session, tema_id: int) -> Lote:
    lote = Lote(tema_id=tema_id)
    s.add(lote)
    return lote


def obtener_lote(s: Session, lote_id: int) -> Lote | None:
    return s.get(Lote, lote_id)


def lotes(s: Session) -> list[Lote]:
    return s.query(Lote).order_by(Lote.id.desc()).all()


def borrar_lotes_de_tema(s: Session, tema_id: int) -> None:
    for lote in s.query(Lote).filter(Lote.tema_id == tema_id).all():
        s.query(Autopiloto).filter(Autopiloto.lote_id == lote.id).update(
            {Autopiloto.lote_id: None}, synchronize_session=False
        )
        s.delete(lote)
