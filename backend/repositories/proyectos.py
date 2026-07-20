from sqlalchemy.orm import Session

from ..models import Proyecto


def crear(s: Session, idea_id: int, slug: str, plantilla: str) -> Proyecto:
    p = Proyecto(idea_id=idea_id, slug=slug, plantilla=plantilla)
    s.add(p)
    return p


def obtener(s: Session, pid: int) -> Proyecto | None:
    return s.get(Proyecto, pid)


def listar(s: Session) -> list[Proyecto]:
    return s.query(Proyecto).order_by(Proyecto.id.desc()).all()


def por_idea(s: Session, idea_id: int) -> Proyecto | None:
    return s.query(Proyecto).filter(Proyecto.idea_id == idea_id).first()


def slug_existe(s: Session, slug: str) -> bool:
    return s.query(Proyecto).filter(Proyecto.slug == slug).first() is not None
