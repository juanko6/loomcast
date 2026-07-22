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


def borrar(s: Session, tema_id: int) -> None:
    """Borra el tema, sus ideas y los jobs de generación que lo referencian."""
    from ..models import Idea, Job

    s.query(Idea).filter(Idea.tema_id == tema_id).delete()
    s.query(Job).filter(Job.tipo == "generar_ideas",
                        Job.ref_id == tema_id).delete()
    s.query(Tema).filter(Tema.id == tema_id).delete()
