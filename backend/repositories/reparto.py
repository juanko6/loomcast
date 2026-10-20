from sqlalchemy.orm import Session

from ..config import REPARTO_DIR
from ..models import MiembroReparto, Personaje


def crear(s: Session, slug: str, nombre: str, clave: str, ficha: str,
          tipo: str, seed: int, voz: str = "") -> MiembroReparto:
    m = MiembroReparto(slug=slug, nombre=nombre, clave=clave, ficha=ficha,
                       tipo=tipo, seed=seed, voz=voz)
    s.add(m)
    return m


def por_slug(s: Session, slug: str) -> MiembroReparto | None:
    return s.query(MiembroReparto).filter(MiembroReparto.slug == slug).first()


def listar(s: Session) -> list[MiembroReparto]:
    return s.query(MiembroReparto).order_by(MiembroReparto.nombre).all()


def borrar(s: Session, miembro: MiembroReparto) -> None:
    s.delete(miembro)


def desvincular(s: Session, slug: str) -> int:
    """Olvida la procedencia en los personajes traídos de `slug` (al borrarlo).

    Los proyectos no pierden nada —su ficha y su retrato son copias— pero sin
    esto quedarían apuntando a un miembro que ya no existe y la UI les seguiría
    ofreciendo "actualizar en el reparto" contra la nada. Mismo criterio que
    `desvincular_voz` al borrar una voz del banco.
    """
    return (
        s.query(Personaje)
        .filter(Personaje.reparto_slug == slug)
        .update({Personaje.reparto_slug: ""}, synchronize_session=False)
    )


def desvincular_voz(s: Session, voz_slug: str) -> int:
    """Deja sin voz a los miembros que usaban `voz_slug` (al borrarla del banco).

    La voz del reparto propio **no** se copia a una carpeta suya como el
    retrato: es una fila del banco, compartida. Así que al borrarla del banco se
    pierde para todos, y lo honesto es que el miembro lo refleje en vez de
    apuntar a un `ref.wav` que ya no está.
    """
    return (
        s.query(MiembroReparto)
        .filter(MiembroReparto.voz == voz_slug)
        .update({MiembroReparto.voz: ""}, synchronize_session=False)
    )


def carpeta(slug: str):
    return REPARTO_DIR / slug


def ruta_retrato(slug: str):
    """La cara guardada del miembro. Nombre fijo dentro de su carpeta, como el
    `ref.wav` de una voz del banco: lo que identifica al recurso es la carpeta."""
    return carpeta(slug) / "retrato.png"
