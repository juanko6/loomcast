from sqlalchemy.orm import Session

from ..models import Proyecto, Serie, SerieMiembro
from . import hilos


def crear(s: Session, slug: str, nombre: str, plantilla: str,
          tema_id: int) -> Serie:
    serie = Serie(slug=slug, nombre=nombre, plantilla=plantilla,
                  tema_id=tema_id)
    s.add(serie)
    return serie


def obtener(s: Session, serie_id: int) -> Serie | None:
    return s.get(Serie, serie_id)


def por_slug(s: Session, slug: str) -> Serie | None:
    return s.query(Serie).filter(Serie.slug == slug).first()


def por_tema(s: Session, tema_id: int) -> Serie | None:
    """La serie dueña de ese tema, si lo es de alguna.

    Es lo que hace que aprobar una idea del tema de una serie cree el episodio
    siguiente en vez de un vídeo suelto, sin un segundo camino para crear
    episodios.
    """
    return s.query(Serie).filter(Serie.tema_id == tema_id).first()


def listar(s: Session) -> list[Serie]:
    return s.query(Serie).order_by(Serie.id.desc()).all()


# --- reparto fijo -----------------------------------------------------------

def miembros(s: Session, serie_id: int) -> list[SerieMiembro]:
    return (
        s.query(SerieMiembro)
        .filter(SerieMiembro.serie_id == serie_id)
        .order_by(SerieMiembro.orden)
        .all()
    )


def anadir_miembro(s: Session, serie_id: int, reparto_slug: str) -> SerieMiembro:
    orden = 1 + max((m.orden for m in miembros(s, serie_id)), default=-1)
    fila = SerieMiembro(serie_id=serie_id, reparto_slug=reparto_slug, orden=orden)
    s.add(fila)
    return fila


def tiene_miembro(s: Session, serie_id: int, reparto_slug: str) -> bool:
    return any(m.reparto_slug == reparto_slug for m in miembros(s, serie_id))


def quitar_miembro(s: Session, serie_id: int, reparto_slug: str) -> int:
    return (
        s.query(SerieMiembro)
        .filter(SerieMiembro.serie_id == serie_id,
                SerieMiembro.reparto_slug == reparto_slug)
        .delete()
    )


def desvincular_reparto(s: Session, reparto_slug: str) -> int:
    """Saca de todas las series al miembro del reparto propio que se borra.

    Aquí no se desvincula "para que la UI no apunte a la nada" como en
    `personajes.desvincular`: estas filas son la orden de traerlo a cada
    episodio nuevo, así que dejarlas haría fallar la creación del siguiente
    episodio con un miembro que ya no existe. Los episodios ya hechos no se
    tocan: tienen su copia de la ficha y de la cara.
    """
    return (
        s.query(SerieMiembro)
        .filter(SerieMiembro.reparto_slug == reparto_slug)
        .delete()
    )


# --- episodios --------------------------------------------------------------

def episodios(s: Session, serie_id: int) -> list[Proyecto]:
    return (
        s.query(Proyecto)
        .filter(Proyecto.serie_id == serie_id)
        .order_by(Proyecto.episodio, Proyecto.id)
        .all()
    )


def siguiente_numero(s: Session, serie_id: int) -> int:
    """El número del próximo episodio: uno más que el mayor que haya.

    Se cuenta sobre el mayor y no sobre cuántos hay para que borrar un episodio
    del medio no cree dos con el mismo número.
    """
    return 1 + max((p.episodio for p in episodios(s, serie_id)), default=0)


def anterior(s: Session, serie_id: int, episodio: int) -> Proyecto | None:
    """El episodio previo al número dado, saltándose los huecos.

    Si se borró el 3, el 4 continúa el 2: lo que importa es de dónde viene la
    historia que el espectador va a oír, no la numeración.
    """
    return (
        s.query(Proyecto)
        .filter(Proyecto.serie_id == serie_id, Proyecto.episodio < episodio)
        .order_by(Proyecto.episodio.desc())
        .first()
    )


def marcar_continuidad_rota(s: Session, serie_id: int, desde: int) -> int:
    """Marca los episodios posteriores a `desde` como escritos sobre otro canon.

    Se llama cuando el canon de un episodio cambia: se reescribió su guion o se
    corrigió su resumen a mano. Los que vienen detrás se escribieron dando por
    cierto lo que decía antes, así que a partir de ahora lo que cuentan puede no
    casar. No se regeneran: regenerar en cascada tiraría guiones ya aprobados, y
    aquí lo hecho no se toca. Se marca y decide el usuario.
    """
    return (
        s.query(Proyecto)
        .filter(Proyecto.serie_id == serie_id, Proyecto.episodio > desde)
        .update({Proyecto.continuidad_rota: True}, synchronize_session=False)
    )


def borrar(s: Session, serie_id: int) -> int:
    """Borra la serie y su reparto fijo, y suelta sus episodios.

    Los episodios **no** se borran: cada uno tiene su guion, su narración, su
    reparto copiado y su vídeo, y perderlos por disolver la serie sería una
    pérdida desproporcionada (el mismo criterio que al borrar un tema con
    proyectos). Quedan como vídeos sueltos, que es lo que son sin serie, y el
    tema de las ideas de episodio también sigue siendo un tema normal.

    SQLite aquí no tiene ON DELETE CASCADE, así que las dependencias se limpian
    a mano o quedarían filas huérfanas. Devuelve cuántos episodios se soltaron.
    """
    s.query(SerieMiembro).filter(SerieMiembro.serie_id == serie_id).delete()
    hilos.borrar_de_serie(s, serie_id)
    sueltos = (
        s.query(Proyecto)
        .filter(Proyecto.serie_id == serie_id)
        .update({Proyecto.serie_id: None, Proyecto.episodio: 0},
                synchronize_session=False)
    )
    s.query(Serie).filter(Serie.id == serie_id).delete()
    return sueltos
