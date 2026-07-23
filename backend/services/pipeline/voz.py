"""Etapa 4 — VOZ: narra el guion COMPLETO en una sola pasada y aplica atempo.

Dos modos (la narración fluye como relato continuo y las pausas las da la
puntuación; después atempo → voz.wav / voz.mp3):

- "clon" (por defecto): clona la voz elegida del banco con el modelo Base
  (generate_voice_clone). Reproduce el timbre del ref pero sin control de
  emoción; requiere proyecto.voz.
- "design": narra con VoiceDesign usando el `instruct` de la plantilla como
  guía de entrega (tono, ritmo, intención). No usa el banco; la voz la diseña
  el modelo desde la descripción. Experimental (más expresivo, identidad menos
  estable entre vídeos).
"""
import json
import subprocess

import numpy as np

from ...clients import tts
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import guiones as guiones_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...repositories import voces as voces_repo


def generar_voz(proyecto_id: int, modo: str = "clon", instruct: str | None = None) -> str:
    import soundfile as sf

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        slug, plantilla = p.slug, p.plantilla
        voz_slug = ref_text = None
        if modo != "design":  # modo clon: necesita una voz del banco lista
            if not p.voz:
                raise ValueError("Selecciona una voz del banco antes de generar la voz")
            voz = voces_repo.por_slug(s, p.voz)
            if voz is None or voz.estado != "lista":
                raise ValueError(f"La voz '{p.voz}' no está disponible")
            voz_slug, ref_text = voz.slug, voz.ref_text

    g = json.loads(guion_row.contenido)
    texto_completo = guiones_repo.texto_narrado(g)
    pl = plantillas_repo.cargar(plantilla)
    ritmo, language = pl["ritmo"], pl["voz"]["language"]

    base_dir = PROYECTOS_DIR / slug
    base_dir.mkdir(parents=True, exist_ok=True)

    if modo == "design":
        # Prioridad: instruct de la UI > el que sugirió el guion para esta
        # historia > el de la plantilla (fallback).
        instruct = (
            (instruct or "").strip()
            or (g.get("voz_instruct") or "").strip()
            or pl["voz"]["instruct"]
        )
        modelo = tts.cargar_modelo(tts.MODELO_DESIGN)
        wavs, sr = modelo.generate_voice_design(
            text=texto_completo,
            language=language,
            instruct=instruct,
            max_new_tokens=8192,
        )
        tts.liberar(modelo)
        etiqueta = "diseñada (VoiceDesign, estilo de la plantilla)"
    else:
        ref_path = voces_repo.ruta_ref(voz_slug)
        if not ref_path.exists():
            raise ValueError(f"Falta el clip de referencia de la voz '{voz_slug}'")
        ref, ref_sr = sf.read(ref_path, dtype="float32")
        base = tts.cargar_modelo(tts.MODELO_BASE)
        prompt = base.create_voice_clone_prompt(ref_audio=(ref, ref_sr), ref_text=ref_text)
        wavs, sr = base.generate_voice_clone(
            text=texto_completo,
            language=language,
            voice_clone_prompt=prompt,
            max_new_tokens=8192,
        )
        tts.liberar(base)
        etiqueta = f"clon '{voz_slug}'"

    sf.write(base_dir / "voz_raw.wav", np.asarray(wavs[0], dtype=np.float32), sr)

    atempo = ritmo.get("atempo", 1.0)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(base_dir / "voz_raw.wav"),
         "-filter:a", f"atempo={atempo}", str(base_dir / "voz.wav")],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(base_dir / "voz.wav"),
         "-b:a", "192k", str(base_dir / "voz.mp3")],
        check=True,
    )

    dur = sf.info(base_dir / "voz.wav").duration
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "VOZ")
        s.commit()
    return f"Voz {etiqueta}: {dur:.1f}s (atempo {atempo})"
