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


def anotar_clip(s: Session, proyecto_id: int, orden: int, modo: str,
                segundos: float) -> None:
    """Deja constancia de con qué modo y en cuánto tiempo se hizo un clip, para
    que la UI pueda decir qué se está mirando cuando el video mezcla modos."""
    for e in por_proyecto(s, proyecto_id):
        if e.orden == orden:
            e.clip_modo, e.clip_s = modo, round(segundos, 1)


def actualizar_prompts(s: Session, proyecto_id: int, prompts: dict[int, dict]) -> int:
    """Reemplaza los prompts (visual y de movimiento) de las escenas indicadas.

    `prompts` va indexado por orden; de cada escena solo se tocan las claves
    presentes, para que editar uno de los dos prompts no borre el otro.
    """
    n = 0
    for e in por_proyecto(s, proyecto_id):
        campos = prompts.get(e.orden)
        if campos is None:
            continue
        if "prompt" in campos:
            e.prompt = campos["prompt"]
        if "prompt_movimiento" in campos:
            e.prompt_movimiento = campos["prompt_movimiento"]
        n += 1
    return n
