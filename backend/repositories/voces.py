from sqlalchemy.orm import Session

from ..config import VOCES_DIR
from ..models import Voz


def crear(s: Session, slug: str, nombre: str, instruct: str) -> Voz:
    voz = Voz(slug=slug, nombre=nombre, instruct=instruct)
    s.add(voz)
    return voz


def obtener(s: Session, voz_id: int) -> Voz | None:
    return s.get(Voz, voz_id)


def por_slug(s: Session, slug: str) -> Voz | None:
    return s.query(Voz).filter(Voz.slug == slug).first()


def borrar(s: Session, voz: Voz) -> None:
    s.delete(voz)


def listar(s: Session) -> list[Voz]:
    return s.query(Voz).order_by(Voz.id).all()


def ruta_ref(slug: str):
    return VOCES_DIR / slug / "ref.wav"
