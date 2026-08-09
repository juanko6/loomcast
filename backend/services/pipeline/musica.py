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
    MUSICA_LM_DEVICE,
    MUSICA_LM_TEMPERATURE,
    MUSICA_LUFS,
    MUSICA_PORTADA_PX,
    MUSICA_TRUE_PEAK,
    PROMPTS_DIR,
)
from . import _masterizar
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
    """Ruta del audio que se sirve, sin conocer la extensión (ACE-Step guarda
    FLAC, pero el workflow puede usar MP3/WAV). Devuelve el primer `musica.*`
    que exista, o None si aún no se ha generado.

    El original sin masterizar vive al lado como `crudo.*`, con otro nombre
    justamente para que este glob no lo pise."""
    car = carpeta(musica_id)
    if car.exists():
        for f in sorted(car.glob("musica.*")):
            return f
    return None


def ruta_portada(musica_id: int):
    """Portada de la pista, o None si aún no se ha generado."""
    p = carpeta(musica_id) / "portada.png"
    return p if p.exists() else None


def generar_portada(musica_id: int) -> str:
    """Genera la portada a partir del prompt que dejó el LLM.

    Va en su propio job encadenado tras `generar_musica`: así solo tienen
    portada las pistas que existen de verdad, y cada regeneración estrena la
    suya. Al ser un job aparte y no parte del de LLM, la cola descarga el
    llama-server antes de pedirle la GPU a ComfyUI.

    Es cuadrada y pequeña a propósito (config: [musica].portada_px): se ve como
    miniatura de 48 px en la lista, y a 384 px cuesta 6 s en el M3 Max frente a
    los 12 s de 512.

    Sin prompt de portada (pista rellenada a mano, sin pasar por el LLM) no
    hace nada: es preferible una miniatura con icono que inventarse una imagen.
    """
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise ValueError(f"Música {musica_id} no existe")
        prompt = m.portada
    if not prompt:
        return "Sin prompt de portada: nada que generar"

    carpeta(musica_id).mkdir(parents=True, exist_ok=True)
    try:
        comfy.generar_imagen(
            prompt,
            random.randint(0, 2**31 - 1),
            carpeta(musica_id) / "portada.png",
            MUSICA_PORTADA_PX,
            MUSICA_PORTADA_PX,
        )
    finally:
        comfy.liberar_memoria()
    return "Portada generada"


def _sistema(tipo: str) -> str:
    nombre = "musica_cancion.md" if tipo == "cancion" else "musica_instrumental.md"
    return (PROMPTS_DIR / nombre).read_text()


def mejorar_prompt(musica_id: int) -> str:
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None:
            raise ValueError(f"Música {musica_id} no existe")
        tipo, idea, duracion_s = m.tipo, m.idea, m.duracion_s

    # La duración va en el mensaje porque el guion de secciones se escala con
    # ella: una pista de 30 s lleva 3 o 4 secciones y una de 180 s, siete u ocho.
    r = llm.chat(_sistema(tipo), f"{idea}\n\n(Duración: {duracion_s} segundos)", MusicaPromptLLM)
    # El guion de secciones también va en instrumental: es lo que evita que la
    # pista sea un mismo bucle repetido durante toda su duración.
    lyrics = r.lyrics

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
            portada=r.portada,
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
        # En canción son la letra cantada; en instrumental, el guion de secciones
        # (solo marcadores [Intro - ...], sin palabras). Los dos van al mismo
        # campo del nodo, que es de donde ACE-Step saca la estructura.
        lyrics = m.lyrics
        duracion_s = m.duracion_s
        bpm, keyscale, timesig, idioma = m.bpm, m.keyscale, m.timesig, m.idioma
        seed = m.seed if m.seed is not None else random.randint(0, 2**31 - 1)

    car = carpeta(musica_id)
    car.mkdir(parents=True, exist_ok=True)
    _limpiar(car)
    try:
        crudo = comfy.generar_musica(
            tags,
            lyrics or "",
            seed,
            duracion_s,
            bpm,
            keyscale,
            timesig,
            idioma,
            car / "musica",
            audio_codes=MUSICA_AUDIO_CODES,
            lm_temperature=MUSICA_LM_TEMPERATURE,
            lm_device=MUSICA_LM_DEVICE,
        )
    finally:
        comfy.liberar_memoria()

    nota = _masterizar_pista(crudo)

    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        musica_repo.marcar_generada(s, m, seed)
        s.commit()
    return f"Pista de música generada{nota}"


def _limpiar(car) -> None:
    """Borra la pista anterior antes de regenerar. Sin esto, una regeneración a
    otro formato dejaría la vieja y `ruta_audio` podría devolverla."""
    for f in list(car.glob("musica.*")) + list(car.glob("crudo.*")):
        f.unlink()


def _masterizar_pista(crudo) -> str:
    """Normaliza la pista recién generada y deja el original como crudo.*

    Si falla, se queda la pista sin masterizar en su sitio: es mejor entregar
    audio crudo que ninguno, y el aviso sube al historial del job.
    """
    if MUSICA_LUFS == 0:
        return ""
    sin_tocar = crudo.with_name(f"crudo{crudo.suffix}")
    crudo.rename(sin_tocar)
    try:
        antes = _masterizar.masterizar(sin_tocar, crudo)
    except _masterizar.MasterizarError as e:
        sin_tocar.rename(crudo)
        return f" (sin masterizar: {e})"
    return (
        f" (masterizada: de {antes['lufs']:.1f} LUFS y pico {antes['pico_dbtp']:.1f} dBTP "
        f"a {MUSICA_LUFS:.0f} LUFS y {MUSICA_TRUE_PEAK:.0f} dBTP)"
    )
