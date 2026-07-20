import json

from sqlalchemy.orm import Session

from ..models import Guion


def ultimo(s: Session, proyecto_id: int) -> Guion | None:
    return (
        s.query(Guion)
        .filter(Guion.proyecto_id == proyecto_id)
        .order_by(Guion.version.desc())
        .first()
    )


def crear(s: Session, proyecto_id: int, contenido: dict) -> Guion:
    """Crea la siguiente versión del guion (el versionado es automático)."""
    previo = ultimo(s, proyecto_id)
    g = Guion(
        proyecto_id=proyecto_id,
        version=(previo.version + 1) if previo else 1,
        contenido=json.dumps(contenido, ensure_ascii=False),
    )
    s.add(g)
    return g
