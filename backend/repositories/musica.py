from sqlalchemy.orm import Session

from ..models import Musica


def crear(
    s: Session,
    tipo: str,
    idea: str,
    tags: str | None,
    lyrics: str | None,
    duracion_s: int,
    bpm: int,
    keyscale: str,
    timesig: str,
    idioma: str,
) -> Musica:
    m = Musica(
        tipo=tipo,
        idea=idea,
        tags=tags or None,
        lyrics=lyrics or None,
        duracion_s=duracion_s,
        bpm=bpm,
        keyscale=keyscale,
        timesig=timesig,
        idioma=idioma,
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
    bpm: int | None = None,
    keyscale: str | None = None,
    timesig: str | None = None,
    idioma: str | None = None,
    portada: str | None = None,
) -> None:
    if tags is not None:
        m.tags = tags or None
    if lyrics is not None:
        m.lyrics = lyrics or None
    if duracion_s is not None:
        m.duracion_s = duracion_s
    if bpm is not None:
        m.bpm = bpm
    if keyscale is not None:
        m.keyscale = keyscale
    if timesig is not None:
        m.timesig = timesig
    if idioma is not None:
        m.idioma = idioma
    if portada is not None:
        m.portada = portada or None


def marcar_generada(s: Session, m: Musica, seed: int) -> None:
    m.seed = seed
    m.estado = "generada"


def borrar(s: Session, m: Musica) -> None:
    s.delete(m)
