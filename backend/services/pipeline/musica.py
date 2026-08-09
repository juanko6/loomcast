"""Generación de música con ACE-Step 1.5, independiente del pipeline de video.

Dos etapas, disparadas por el usuario desde la UI:
  1. mejorar_prompt (opcional) — el LLM convierte la idea en una descripción de
     estilo en prosa, el tempo/tonalidad/compás, y si es canción la letra con
     marcadores [Verse 1 - ...].
  2. generar — ACE-Step 1.5 (vía ComfyUI) sintetiza la pista de audio.

El modo (`tipo`) decide qué prompt de sistema usa la etapa 1 y si se envía letra
a la etapa 2: "instrumental" (música de fondo / jingle, sin voz) o "cancion".
"""
import random

from ...clients import comfy, llm
from ...config import (
    MUSICA_AUDIO_CODES,
    MUSICA_DIR,
    MUSICA_LM_TEMPERATURE,
    PROMPTS_DIR,
)
from ...db import get_session
from ...repositories import musica as musica_repo
from ...schemas import MusicaPromptLLM
from ..musica_combos import (
    normalizar_bpm,
    normalizar_idioma,
    normalizar_keyscale,
    normalizar_timesig,
)


def carpeta(musica_id: int):
    return MUSICA_DIR / str(musica_id)


def ruta_audio(musica_id: int):
    """Ruta del audio generado sin conocer la extensión (ACE-Step guarda FLAC,
    pero el workflow puede usar MP3/WAV). Devuelve el primer `musica.*` que
    exista, o None si aún no se ha generado."""
    car = carpeta(musica_id)
    if car.exists():
        for f in sorted(car.glob("musica.*")):
            return f
    return None


def _sistema(tipo: str) -> str:
    nombre = "musica_cancion.md" if tipo == "cancion" else "musica_instrumental.md"
    return (PROMPTS_DIR / nombre).read_text()


def mejorar_prompt(musica_id: int) -> str:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise ValueError(f"Música {musica_id} no existe")
        tipo, idea = m.tipo, m.idea

    r = llm.chat(_sistema(tipo), idea, MusicaPromptLLM)
    lyrics = r.lyrics if tipo == "cancion" else ""

    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        # El LLM propone tempo/tonalidad/compás/idioma, pero son combos cerrados
        # del nodo: se normalizan antes de guardar o el workflow revienta.
        musica_repo.guardar_campos(
            s,
            m,
            r.tags,
            lyrics,
            None,
            bpm=normalizar_bpm(r.bpm),
            keyscale=normalizar_keyscale(r.keyscale),
            timesig=normalizar_timesig(r.timesig),
            idioma=normalizar_idioma(r.idioma if tipo == "cancion" else "en"),
        )
        s.commit()
    return "Estilo, tempo y letra sugeridos"


def generar(musica_id: int) -> str:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise ValueError(f"Música {musica_id} no existe")
        if not m.tags:
            raise ValueError("La pista no tiene etiquetas de estilo todavía")
        tipo = m.tipo
        tags = m.tags
        lyrics = m.lyrics if tipo == "cancion" else ""
        duracion_s = m.duracion_s
        bpm, keyscale, timesig, idioma = m.bpm, m.keyscale, m.timesig, m.idioma
        seed = m.seed if m.seed is not None else random.randint(0, 2**31 - 1)

    carpeta(musica_id).mkdir(parents=True, exist_ok=True)
    try:
        comfy.generar_musica(
            tags,
            lyrics or "",
            seed,
            duracion_s,
            bpm,
            keyscale,
            timesig,
            idioma,
            carpeta(musica_id) / "musica",
            audio_codes=MUSICA_AUDIO_CODES,
            lm_temperature=MUSICA_LM_TEMPERATURE,
        )
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        musica_repo.marcar_generada(s, m, seed)
        s.commit()
    return "Pista de música generada"
