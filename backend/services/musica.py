"""Lógica de la sección de música (crear, editar campos, detalle, borrar).

Las etapas pesadas (mejorar prompt con el LLM, generar con ACE-Step) viven en
`pipeline/musica.py` y se disparan por la cola de jobs; aquí queda lo que
atiende directamente a la API HTTP.
"""
import shutil

from ..db import get_session
from ..repositories import jobs as jobs_repo
from ..repositories import musica as musica_repo
from ..repositories import proyectos as proyectos_repo
from ..services.pipeline import musica as musica_pipeline
from ..workers import queue
from .musica_combos import (
    BPM_DEFECTO,
    IDIOMA_DEFECTO,
    KEYSCALE_DEFECTO,
    TIMESIG_DEFECTO,
    normalizar_bpm,
    normalizar_idioma,
    normalizar_keyscale,
    normalizar_timesig,
)

TIPOS_JOB = ["mejorar_prompt_musica", "generar_musica", "generar_portada_musica",
             "escribir_pista_album"]
# Tope de duración en segundos (ACE-Step 1.5 llega a ~10 min; se acota para no
# encolar generaciones eternas por error).
DUR_MIN, DUR_MAX = 5, 600


class MusicaNoExiste(LookupError):
    pass


def _normalizar_dur(v: int) -> int:
    return max(DUR_MIN, min(DUR_MAX, int(v)))


def crear(
    tipo: str,
    idea: str,
    tags: str,
    lyrics: str,
    duracion_s: int,
    bpm: int | None = None,
    keyscale: str | None = None,
    timesig: str | None = None,
    idioma: str | None = None,
) -> dict:
    t = "cancion" if tipo == "cancion" else "instrumental"
    with get_session() as s:
        m = musica_repo.crear(
            s,
            t,
            idea.strip(),
            tags.strip(),
            lyrics.strip(),
            _normalizar_dur(duracion_s),
            normalizar_bpm(bpm if bpm is not None else BPM_DEFECTO),
            normalizar_keyscale(keyscale if keyscale is not None else KEYSCALE_DEFECTO),
            normalizar_timesig(timesig if timesig is not None else TIMESIG_DEFECTO),
            # Una pista instrumental no canta: el idioma solo importa en canción,
            # y para instrumental "en" es lo que usan las plantillas oficiales.
            normalizar_idioma(
                idioma
                if idioma is not None
                else (IDIOMA_DEFECTO if t == "cancion" else "en")
            ),
        )
        s.commit()
        return {"id": m.id}


def editar_campos(
    musica_id: int,
    tags: str | None,
    lyrics: str | None,
    duracion_s: int | None,
    bpm: int | None = None,
    keyscale: str | None = None,
    timesig: str | None = None,
    idioma: str | None = None,
) -> None:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise MusicaNoExiste(musica_id)
        musica_repo.guardar_campos(s, m, tags, lyrics, *_musicales(
            duracion_s, bpm, keyscale, timesig, idioma
        ))
        s.commit()


def _musicales(
    duracion_s: int | None,
    bpm: int | None,
    keyscale: str | None,
    timesig: str | None,
    idioma: str | None,
) -> tuple:
    """Normaliza los campos musicales dejando los None como None (no tocar)."""
    return (
        _normalizar_dur(duracion_s) if duracion_s is not None else None,
        normalizar_bpm(bpm) if bpm is not None else None,
        normalizar_keyscale(keyscale) if keyscale is not None else None,
        normalizar_timesig(timesig) if timesig is not None else None,
        normalizar_idioma(idioma) if idioma is not None else None,
    )


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
    bpm: int | None = None,
    keyscale: str | None = None,
    timesig: str | None = None,
    idioma: str | None = None,
) -> int:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise MusicaNoExiste(musica_id)
        musica_repo.guardar_campos(s, m, tags, lyrics, *_musicales(
            duracion_s, bpm, keyscale, timesig, idioma
        ))
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
        "bpm": m.bpm,
        "keyscale": m.keyscale,
        "timesig": m.timesig,
        "idioma": m.idioma,
        "seed": m.seed,
        "estado": m.estado,
        "tiene_audio": musica_pipeline.ruta_audio(m.id) is not None,
        "tiene_portada": musica_pipeline.ruta_portada(m.id) is not None,
        "ocupado": _ocupado(s, m.id),
        "album_id": m.album_id,
        "titulo": m.titulo,
        "intencion": m.intencion,
    }


def listar() -> list[dict]:
    with get_session() as s:
        return [
            {
                "id": m.id,
                "tipo": m.tipo,
                "idea": m.idea,
                "estado": m.estado,
                "tiene_portada": musica_pipeline.ruta_portada(m.id) is not None,
                "album_id": m.album_id,
            }
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
        # Un proyecto puede estar usándola como su banda sonora: se queda sin
        # música (y sin mezcla) en vez de apuntar a una pista que ya no existe.
        desvinculados = proyectos_repo.desvincular_musica(s, musica_id)
        musica_repo.borrar(s, m)
        s.commit()
    car = musica_pipeline.carpeta(musica_id)
    archivos = 0
    if car.exists():
        archivos = sum(1 for _ in car.rglob("*") if _.is_file())
        shutil.rmtree(car)
    return {"borrada": musica_id, "archivos": archivos,
            "proyectos_desvinculados": desvinculados}
