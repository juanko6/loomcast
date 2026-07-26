from sqlalchemy.orm import Session

from ..models import Musica


def crear(
    s: Session,
    tipo: str,
    idea: str,
    tags: str | None,
    lyrics: str | None,
    duracion_s: int,
) -> Musica:
    m = Musica(
        tipo=tipo,
        idea=idea,
        tags=tags or None,
        lyrics=lyrics or None,
        duracion_s=duracion_s,
    )
    s.add(m)
    return m


def obtener(s: Session, musica_id: int) -> Musica | None:
    return s.get(Musica, musica_id)


def listar(s: Session) -> list[Musica]:
    return s.query(Musica).order_by(Musica.id.desc()).all()


def guardar_campos(
    s: Session,
    m: Musica,
    tags: str | None,
    lyrics: str | None,
    duracion_s: int | None,
) -> None:
    if tags is not None:
        m.tags = tags or None
    if lyrics is not None:
        m.lyrics = lyrics or None
    if duracion_s is not None:
        m.duracion_s = duracion_s


def marcar_generada(s: Session, m: Musica, seed: int) -> None:
    m.seed = seed
    m.estado = "generada"


def borrar(s: Session, m: Musica) -> None:
    s.delete(m)
