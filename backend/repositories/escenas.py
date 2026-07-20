from sqlalchemy.orm import Session

from ..models import Escena


def reemplazar_todas(s: Session, proyecto_id: int, escenas: list[dict]) -> list[Escena]:
    """Regenerar escenas siempre reemplaza el set completo del proyecto."""
    s.query(Escena).filter(Escena.proyecto_id == proyecto_id).delete()
    filas = [Escena(proyecto_id=proyecto_id, **e) for e in escenas]
    s.add_all(filas)
    return filas


def por_proyecto(s: Session, proyecto_id: int) -> list[Escena]:
    return (
        s.query(Escena)
        .filter(Escena.proyecto_id == proyecto_id)
        .order_by(Escena.orden)
        .all()
    )


def actualizar_prompts(s: Session, proyecto_id: int, prompts: dict[int, str]) -> int:
    """Reemplaza el prompt visual de las escenas indicadas (por orden)."""
    n = 0
    for e in por_proyecto(s, proyecto_id):
        if e.orden in prompts:
            e.prompt = prompts[e.orden]
            n += 1
    return n
