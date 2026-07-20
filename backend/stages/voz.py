"""Etapa 4 — VOZ: Qwen3-TTS con "design then clone".

1. VoiceDesign crea un clip de referencia según la descripción de voz de la
   plantilla (voz distinta por proyecto, consistente dentro del video).
2. El modelo Base convierte ese clip en un voice_clone_prompt reutilizable
   (guardado como voz_ref.wav para futuras regeneraciones parciales).
3. generate_voice_clone sintetiza el guion COMPLETO en una sola pasada:
   la narración fluye como relato continuo y las pausas las da la puntuación.
4. atempo → voz.wav / voz.mp3.
"""
import gc
import json
import subprocess

import numpy as np

from .. import plantillas
from ..config import PROYECTOS_DIR
from ..db import get_session
from ..models import Guion, Proyecto

MODELO_DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
MODELO_BASE = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

# Texto fijo de calibración para el clip de referencia (neutro, con pregunta
# y número para que el clon capture entonación variada).
REF_TEXT = (
    "Esta es la voz oficial de este canal. ¿Lista para contar una historia "
    "increíble? Empezamos en 3, 2, 1."
)

ORDEN_ESTADOS = [
    "IDEA", "GUION", "METADATOS", "VOZ", "SUBTITULOS", "ESCENAS",
    "IMAGENES", "UPSCALE", "CLIPS", "INTERPOLADO", "FINAL",
]


def avanzar_estado(proyecto: Proyecto, nuevo: str) -> None:
    if ORDEN_ESTADOS.index(nuevo) > ORDEN_ESTADOS.index(proyecto.estado):
        proyecto.estado = nuevo


def _cargar_modelo(repo: str):
    import torch
    from qwen_tts import Qwen3TTSModel

    return Qwen3TTSModel.from_pretrained(
        repo, device_map="mps", dtype=torch.bfloat16, attn_implementation="sdpa"
    )


def _liberar(modelo) -> None:
    import torch

    del modelo
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


def generar_voz(proyecto_id: int) -> str:
    import soundfile as sf

    with get_session() as s:
        p = s.get(Proyecto, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = (
            s.query(Guion).filter(Guion.proyecto_id == proyecto_id)
            .order_by(Guion.version.desc()).first()
        )
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        slug, plantilla = p.slug, p.plantilla

    g = json.loads(guion_row.contenido)
    texto_completo = " ".join([g["gancho"], *g["frases"], g["cta"]])
    pl = plantillas.cargar(plantilla)
    voz_cfg = pl["voz"]
    ritmo = pl["ritmo"]

    base_dir = PROYECTOS_DIR / slug
    base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Referencia con VoiceDesign
    design = _cargar_modelo(MODELO_DESIGN)
    ref_wavs, sr = design.generate_voice_design(
        text=REF_TEXT, language=voz_cfg["language"], instruct=voz_cfg["instruct"]
    )
    ref = np.asarray(ref_wavs[0], dtype=np.float32)
    sf.write(base_dir / "voz_ref.wav", ref, sr)
    _liberar(design)

    # 2-3. Clonar la referencia y narrar el guion completo en una sola pasada
    base = _cargar_modelo(MODELO_BASE)
    prompt = base.create_voice_clone_prompt(ref_audio=(ref, sr), ref_text=REF_TEXT)
    wavs, sr = base.generate_voice_clone(
        text=texto_completo,
        language=voz_cfg["language"],
        voice_clone_prompt=prompt,
        max_new_tokens=8192,
    )
    _liberar(base)

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
        p = s.get(Proyecto, proyecto_id)
        avanzar_estado(p, "VOZ")
        s.commit()
    return f"Voz generada (narración continua): {dur:.1f}s (atempo {atempo})"
