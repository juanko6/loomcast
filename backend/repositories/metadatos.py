import json

from sqlalchemy.orm import Session

from ..models import Metadatos


def ultimo(s: Session, proyecto_id: int) -> Metadatos | None:
    return (
        s.query(Metadatos)
        .filter(Metadatos.proyecto_id == proyecto_id)
        .order_by(Metadatos.version.desc())
        .first()
    )


def crear(s: Session, proyecto_id: int, contenido: dict) -> Metadatos:
    previo = ultimo(s, proyecto_id)
    m = Metadatos(
        proyecto_id=proyecto_id,
        version=(previo.version + 1) if previo else 1,
        contenido=json.dumps(contenido, ensure_ascii=False),
    )
    s.add(m)
    return m
