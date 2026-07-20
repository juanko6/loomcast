from sqlalchemy.orm import Session

from ..models import Tema


def crear(s: Session, texto: str, plantilla: str) -> Tema:
    tema = Tema(texto=texto, plantilla=plantilla)
    s.add(tema)
    return tema


def obtener(s: Session, tema_id: int) -> Tema | None:
    return s.get(Tema, tema_id)


def listar(s: Session) -> list[Tema]:
    return s.query(Tema).order_by(Tema.id.desc()).all()
