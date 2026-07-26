"""Lógica de la sección de música (crear, editar campos, detalle, borrar).

Las etapas pesadas (mejorar prompt con el LLM, generar con ACE-Step) viven en
`pipeline/musica.py` y se disparan por la cola de jobs; aquí queda lo que
atiende directamente a la API HTTP.
"""
import shutil

from ..db import get_session
from ..repositories import jobs as jobs_repo
from ..repositories import musica as musica_repo
from ..services.pipeline import musica as musica_pipeline
from ..workers import queue

TIPOS_JOB = ["mejorar_prompt_musica", "generar_musica"]
# Tope de duración en segundos (ACE-Step 1.5 llega a ~10 min; se acota para no
# encolar generaciones eternas por error).
DUR_MIN, DUR_MAX = 5, 600


class MusicaNoExiste(LookupError):
    pass


def _normalizar_dur(v: int) -> int:
    return max(DUR_MIN, min(DUR_MAX, int(v)))


def crear(tipo: str, idea: str, tags: str, lyrics: str, duracion_s: int) -> dict:
    t = "cancion" if tipo == "cancion" else "instrumental"
    with get_session() as s:
        m = musica_repo.crear(
            s, t, idea.strip(), tags.strip(), lyrics.strip(), _normalizar_dur(duracion_s)
        )
        s.commit()
        return {"id": m.id}


def editar_campos(
    musica_id: int,
    tags: str | None,
    lyrics: str | None,
    duracion_s: int | None,
) -> None:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise MusicaNoExiste(musica_id)
        dur = _normalizar_dur(duracion_s) if duracion_s is not None else None
        musica_repo.guardar_campos(s, m, tags, lyrics, dur)
        s.commit()


def mejorar(musica_id: int) -> int:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise MusicaNoExiste(musica_id)
    return queue.encolar("mejorar_prompt_musica", musica_id)


def generar(
    musica_id: int,
    tags: str | None,
    lyrics: str | None,
    duracion_s: int | None,
    seed: int | None,
) -> int:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise MusicaNoExiste(musica_id)
        dur = _normalizar_dur(duracion_s) if duracion_s is not None else None
        musica_repo.guardar_campos(s, m, tags, lyrics, dur)
        # seed None = pista nueva (el pipeline elige una aleatoria); un seed
        # concreto reproduce la misma pista.
        m.seed = seed
        s.commit()
    return queue.encolar("generar_musica", musica_id)


def _ocupado(s, musica_id: int) -> bool:
    return any(
        j.ref_id == musica_id and j.tipo in TIPOS_JOB
        for j in jobs_repo.activos(s)
    )


def _a_dict(s, m) -> dict:
    return {
        "id": m.id,
        "tipo": m.tipo,
        "idea": m.idea,
        "tags": m.tags,
        "lyrics": m.lyrics,
        "duracion_s": m.duracion_s,
        "seed": m.seed,
        "estado": m.estado,
        "tiene_audio": musica_pipeline.ruta_audio(m.id) is not None,
        "ocupado": _ocupado(s, m.id),
    }


def listar() -> list[dict]:
    with get_session() as s:
        return [
            {"id": m.id, "tipo": m.tipo, "idea": m.idea, "estado": m.estado}
            for m in musica_repo.listar(s)
        ]


def detalle(musica_id: int) -> dict:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise MusicaNoExiste(musica_id)
        return _a_dict(s, m)


def borrar(musica_id: int) -> dict:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise MusicaNoExiste(musica_id)
        musica_repo.borrar(s, m)
        s.commit()
    car = musica_pipeline.carpeta(musica_id)
    archivos = 0
    if car.exists():
        archivos = sum(1 for _ in car.rglob("*") if _.is_file())
        shutil.rmtree(car)
    return {"borrada": musica_id, "archivos": archivos}
