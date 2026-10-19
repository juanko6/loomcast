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


def borrar(s: Session, pid: int) -> None:
    """Borra el proyecto y todo lo que cuelga de él (escenas, personajes,
    guiones, metadatos y sus jobs). SQLite aquí no tiene ON DELETE CASCADE, así
    que las dependencias se limpian a mano o quedarían filas huérfanas."""
    from ..models import Escena, Guion, Job, Metadatos, Personaje

    for modelo in (Escena, Personaje, Guion, Metadatos):
        s.query(modelo).filter(modelo.proyecto_id == pid).delete()
    s.query(Job).filter(Job.ref_id == pid).delete()
    s.query(Proyecto).filter(Proyecto.id == pid).delete()


def slug_existe(s: Session, slug: str) -> bool:
    return s.query(Proyecto).filter(Proyecto.slug == slug).first() is not None


def desvincular_musica(s: Session, musica_id: int) -> int:
    """Deja sin música los proyectos que apuntaban a `musica_id` (al borrar esa
    pista desde la sección de Música). Sin esto, un proyecto con la mezcla
    activada se quedaría apuntando a una pista que ya no existe y el armado
    fallaría. Devuelve cuántos se desvincularon."""
    return (
        s.query(Proyecto)
        .filter(Proyecto.musica_id == musica_id)
        .update(
            {Proyecto.musica_id: None, Proyecto.musica_mezclar: False},
            synchronize_session=False,
        )
    )


def desvincular_voz(s: Session, voz_slug: str) -> int:
    """Deja sin voz los proyectos que usaban `voz_slug` (al borrar esa voz),
    para no dejar referencias colgadas. Devuelve cuántos se desvincularon."""
    return (
        s.query(Proyecto)
        .filter(Proyecto.voz == voz_slug)
        .update({Proyecto.voz: None}, synchronize_session=False)
    )
