from sqlalchemy.orm import Session

from ..models import Idea


def crear(s: Session, tema_id: int, titulo: str, gancho: str, resumen: str) -> Idea:
    idea = Idea(tema_id=tema_id, titulo=titulo, gancho=gancho, resumen=resumen)
    s.add(idea)
    return idea


def obtener(s: Session, idea_id: int) -> Idea | None:
    return s.get(Idea, idea_id)


def por_tema(s: Session, tema_id: int) -> list[Idea]:
    return s.query(Idea).filter(Idea.tema_id == tema_id).order_by(Idea.id).all()
