"""Álbumes de música: crear, revisar, editar y lanzar.

Las etapas pesadas viven en `pipeline/album.py` y van por la cola; aquí queda lo
que atiende la API. Las pistas de un álbum son `Musica` normales: se oyen, se
descargan y se usan de banda sonora igual que una suelta.
"""
import random
import shutil

from ..db import get_session
from ..repositories import albumes as albumes_repo
from ..repositories import jobs as jobs_repo
from ..repositories import musica as musica_repo
from ..repositories import proyectos as proyectos_repo
from ..services.pipeline import album as album_pipeline
from ..services.pipeline import musica as musica_pipeline
from ..workers import queue
from . import musica_compases as compases
from .musica_combos import normalizar_bpm, normalizar_keyscale, normalizar_timesig

PISTAS_MIN, PISTAS_MAX = 2, 20
TIPOS_JOB_ALBUM = ["planificar_album", "escribir_album", "generar_portada_album"]
TIPOS_JOB_PISTA = ["escribir_pista_album", "generar_musica", "generar_portada_musica"]


class AlbumNoExiste(LookupError):
    pass


class AlbumInvalido(ValueError):
    pass


def _num(n: int) -> int:
    return max(PISTAS_MIN, min(PISTAS_MAX, int(n)))


def crear_desde_idea(idea: str, num_pistas: int) -> dict:
    if not idea.strip():
        raise AlbumInvalido("Escribe una idea para el álbum")
    with get_session() as s:
        a = albumes_repo.crear(s, idea.strip(), _num(num_pistas),
                               random.randint(0, 2**31 - 1), None)
        s.commit()
        album_id = a.id
    queue.encolar("planificar_album", album_id)
    return {"id": album_id}


def crear_desde_pista(musica_id: int, num_pistas: int) -> dict:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise AlbumInvalido("La pista no existe")
        if m.album_id is not None:
            raise AlbumInvalido("La pista ya es de un álbum")
        if m.tipo != "instrumental" or not m.tags:
            raise AlbumInvalido("El álbum sale de una pista instrumental con descripción")
        # La semilla del álbum es la de la pista que gustó: todas comparten la
        # misma y lo único que cambia entre ellas es la intención.
        seed = m.seed if m.seed is not None else random.randint(0, 2**31 - 1)
        a = albumes_repo.crear(s, m.idea, _num(num_pistas), seed, musica_id)
        s.commit()
        album_id = a.id
    queue.encolar("planificar_album", album_id)
    return {"id": album_id}


def _jobs_activos(s) -> list:
    return jobs_repo.activos(s)


def _pista_dict(m, origen_id, activos) -> dict:
    return {
        "id": m.id,
        "pista_n": m.pista_n,
        "titulo": m.titulo,
        "intencion": m.intencion,
        "tags": m.tags,
        "lyrics": m.lyrics,
        "bpm": m.bpm,
        "keyscale": m.keyscale,
        "timesig": m.timesig,
        "duracion_s": m.duracion_s,
        "compases": compases.total_compases(m.lyrics or ""),
        "estado": m.estado,
        "seed": m.seed,
        "origen": m.id == origen_id,
        "escrita": bool(m.tags),
        "tiene_audio": musica_pipeline.ruta_audio(m.id) is not None,
        "tiene_portada": musica_pipeline.ruta_portada(m.id) is not None,
        "ocupado": any(j.ref_id == m.id and j.tipo in TIPOS_JOB_PISTA for j in activos),
    }


def detalle(album_id: int) -> dict:
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise AlbumNoExiste(album_id)
        activos = _jobs_activos(s)
        pistas = [_pista_dict(m, a.origen_musica_id, activos)
                  for m in albumes_repo.pistas(s, album_id)]
        return {
            "id": a.id,
            "titulo": a.titulo,
            "idea": a.idea,
            "num_pistas": a.num_pistas,
            "origen_musica_id": a.origen_musica_id,
            "genero": a.genero,
            "banda": [b for b in a.banda.splitlines() if b.strip()],
            "firma": a.firma,
            "arco": a.arco,
            "seed": a.seed,
            "estado": a.estado,
            "tiene_portada": album_pipeline.ruta_portada(a.id) is not None,
            "ocupado": any(j.ref_id == a.id and j.tipo in TIPOS_JOB_ALBUM for j in activos),
            "duracion_total_s": sum(p["duracion_s"] for p in pistas if p["escrita"]),
            "pistas": pistas,
        }


def listar() -> list[dict]:
    with get_session() as s:
        activos = _jobs_activos(s)
        out = []
        for a in albumes_repo.listar(s):
            pistas = albumes_repo.pistas(s, a.id)
            out.append({
                "id": a.id,
                "titulo": a.titulo or a.idea[:60] or f"Álbum {a.id}",
                "estado": a.estado,
                "num_pistas": len(pistas) or a.num_pistas,
                "generadas": sum(1 for m in pistas if m.estado == "generada"),
                "tiene_portada": album_pipeline.ruta_portada(a.id) is not None,
                "ocupado": any(j.ref_id == a.id and j.tipo in TIPOS_JOB_ALBUM
                               for j in activos),
            })
        return out


def editar(album_id: int, titulo: str | None, firma: str | None) -> None:
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise AlbumNoExiste(album_id)
        if titulo is not None and titulo.strip():
            a.titulo = titulo.strip()
        if firma is not None:
            # La firma va pegada al final de cada brief ya escrito: cambiarla
            # cambia esa cola en todas las pistas, para que sigan iguales.
            vieja, nueva = a.firma.strip(), firma.strip()
            if vieja != nueva:
                for m in albumes_repo.pistas(s, album_id):
                    if m.tags and m.id != a.origen_musica_id and vieja and m.tags.endswith(vieja):
                        m.tags = f"{m.tags[: -len(vieja)].rstrip()} {nueva}".strip()
                a.firma = nueva
        s.commit()


def _pista(s, album_id: int, musica_id: int):
    m = musica_repo.obtener(s, musica_id)
    if m is None or m.album_id != album_id:
        raise AlbumNoExiste(musica_id)
    return m


def editar_pista(
    album_id: int,
    musica_id: int,
    titulo: str | None = None,
    intencion: str | None = None,
    bpm: int | None = None,
    keyscale: str | None = None,
    timesig: str | None = None,
) -> None:
    with get_session() as s:
        m = _pista(s, album_id, musica_id)
        if titulo is not None and titulo.strip():
            m.titulo = titulo.strip()
            m.idea = m.titulo
        if intencion is not None:
            m.intencion = intencion.strip()
        if bpm is not None:
            m.bpm = normalizar_bpm(bpm)
        if keyscale is not None:
            m.keyscale = normalizar_keyscale(keyscale)
        if timesig is not None:
            m.timesig = normalizar_timesig(timesig)
        # Los compases no cambian con el tempo; la duración sí. Así un tema que
        # se acelera sigue terminando donde termina su guion.
        dur = compases.duracion_desde_guion(m.lyrics or "", m.bpm, m.timesig)
        if dur is not None:
            m.duracion_s = max(album_pipeline.DUR_MIN, min(album_pipeline.DUR_MAX, dur))
        s.commit()


def reescribir_pista(album_id: int, musica_id: int) -> int:
    with get_session() as s:
        m = _pista(s, album_id, musica_id)
        a = albumes_repo.obtener(s, album_id)
        if m.id == a.origen_musica_id:
            raise AlbumInvalido("La pista de origen no se reescribe: es la referencia")
    return queue.encolar("escribir_pista_album", musica_id)


def _renumerar(s, album_id: int) -> None:
    for i, m in enumerate(albumes_repo.pistas(s, album_id), start=1):
        m.pista_n = i


def quitar_pista(album_id: int, musica_id: int) -> None:
    """Saca una pista del álbum. La de origen vuelve a ser suelta; las demás
    se borran con su audio."""
    with get_session() as s:
        m = _pista(s, album_id, musica_id)
        a = albumes_repo.obtener(s, album_id)
        borrar_archivos = m.id != a.origen_musica_id
        if borrar_archivos:
            # Un proyecto puede usarla de banda sonora: se queda sin música.
            proyectos_repo.desvincular_musica(s, m.id)
            musica_repo.borrar(s, m)
        else:
            m.album_id = m.pista_n = None
            a.origen_musica_id = None
        s.flush()
        _renumerar(s, album_id)
        s.commit()
    if borrar_archivos:
        shutil.rmtree(musica_pipeline.carpeta(musica_id), ignore_errors=True)


def ordenar(album_id: int, ids: list[int]) -> None:
    with get_session() as s:
        if albumes_repo.obtener(s, album_id) is None:
            raise AlbumNoExiste(album_id)
        pistas = {m.id: m for m in albumes_repo.pistas(s, album_id)}
        if sorted(ids) != sorted(pistas):
            raise AlbumInvalido("El orden tiene que nombrar todas las pistas del álbum")
        for i, mid in enumerate(ids, start=1):
            pistas[mid].pista_n = i
        s.commit()


def replanificar(album_id: int) -> int:
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise AlbumNoExiste(album_id)
        a.estado = "planificando"
        s.commit()
    return queue.encolar("planificar_album", album_id)


def producir(album_id: int) -> dict:
    """Encola la síntesis de las pistas escritas que aún no tienen audio, todas
    con la semilla del álbum, y la portada del disco detrás de la última."""
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise AlbumNoExiste(album_id)
        pistas = albumes_repo.pistas(s, album_id)
        sin_escribir = [m.pista_n for m in pistas if not m.tags]
        if sin_escribir:
            raise AlbumInvalido(
                f"Faltan por escribir las pistas {', '.join(map(str, sin_escribir))}"
            )
        ids = [m.id for m in pistas if m.estado != "generada"]
        for m in pistas:
            if m.id in ids:
                m.seed = a.seed
        a.estado = "produciendo"
        s.commit()
    jobs = [queue.encolar("generar_musica", mid) for mid in ids]
    jobs.append(queue.encolar("generar_portada_album", album_id))
    return {"pistas": len(ids), "jobs": jobs}


def borrar(album_id: int) -> dict:
    """Borra el álbum y sus pistas nuevas. La de origen vuelve a ser suelta."""
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise AlbumNoExiste(album_id)
        borradas = []
        for m in albumes_repo.pistas(s, album_id):
            if m.id == a.origen_musica_id:
                m.album_id = m.pista_n = None
            else:
                borradas.append(m.id)
                proyectos_repo.desvincular_musica(s, m.id)
                musica_repo.borrar(s, m)
        albumes_repo.borrar(s, a)
        s.commit()
    for mid in borradas:
        shutil.rmtree(musica_pipeline.carpeta(mid), ignore_errors=True)
    shutil.rmtree(album_pipeline.carpeta(album_id), ignore_errors=True)
    return {"borrado": album_id, "pistas_borradas": len(borradas)}
