from sqlalchemy.orm import Session

from ..models import Album, Musica


def crear(s: Session, idea: str, num_pistas: int, seed: int,
          origen_musica_id: int | None) -> Album:
    a = Album(idea=idea, num_pistas=num_pistas, seed=seed,
              origen_musica_id=origen_musica_id)
    s.add(a)
    return a


def obtener(s: Session, album_id: int) -> Album | None:
    return s.get(Album, album_id)


def listar(s: Session) -> list[Album]:
    return s.query(Album).order_by(Album.id.desc()).all()


def pistas(s: Session, album_id: int) -> list[Musica]:
    """Las pistas del álbum en su orden."""
    return (
        s.query(Musica)
        .filter(Musica.album_id == album_id)
        .order_by(Musica.pista_n, Musica.id)
        .all()
    )


def titulos_usados(s: Session, salvo_album_id: int) -> tuple[list[str], list[str]]:
    """(títulos de otros álbumes, títulos de sus pistas). Con la misma idea y
    el mismo género el LLM converge en los mismos nombres, y un segundo álbum
    de jazz salía llamándose igual que el primero, con sus pistas repetidas."""
    discos = [
        t for (t,) in s.query(Album.titulo).filter(Album.id != salvo_album_id)
        if t
    ]
    temas = [
        t for (t,) in s.query(Musica.titulo)
        .filter(Musica.album_id.isnot(None), Musica.album_id != salvo_album_id)
        if t
    ]
    return discos, temas


def borrar(s: Session, a: Album) -> None:
    s.delete(a)
