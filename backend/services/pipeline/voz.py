"""Etapa 4 — VOZ: Qwen3-TTS con "design then clone".

1. VoiceDesign crea un clip de referencia según la descripción de voz de la
   plantilla (voz distinta por proyecto, consistente dentro del video).
2. El modelo Base convierte ese clip en un voice_clone_prompt reutilizable
   (guardado como voz_ref.wav para futuras regeneraciones parciales).
3. generate_voice_clone sintetiza el guion COMPLETO en una sola pasada:
   la narración fluye como relato continuo y las pausas las da la puntuación.
4. atempo → voz.wav / voz.mp3.
"""
import json
import subprocess

import numpy as np

from ...clients import tts
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...repositories import guiones as guiones_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...models import avanzar_estado

# Texto fijo de calibración para el clip de referencia (neutro, con pregunta
# y número para que el clon capture entonación variada).
REF_TEXT = (
    "Esta es la voz oficial de este canal. ¿Lista para contar una historia "
    "increíble? Empezamos en 3, 2, 1."
)


def generar_voz(proyecto_id: int) -> str:
    import soundfile as sf

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        slug, plantilla = p.slug, p.plantilla

    g = json.loads(guion_row.contenido)
    texto_completo = " ".join([g["gancho"], *g["frases"], g["cta"]])
    pl = plantillas_repo.cargar(plantilla)
    voz_cfg = pl["voz"]
    ritmo = pl["ritmo"]

    base_dir = PROYECTOS_DIR / slug
    base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Referencia con VoiceDesign
    design = tts.cargar_modelo(tts.MODELO_DESIGN)
    ref_wavs, sr = design.generate_voice_design(
        text=REF_TEXT, language=voz_cfg["language"], instruct=voz_cfg["instruct"]
    )
    ref = np.asarray(ref_wavs[0], dtype=np.float32)
    sf.write(base_dir / "voz_ref.wav", ref, sr)
    tts.liberar(design)

    # 2-3. Clonar la referencia y narrar el guion completo en una sola pasada
    base = tts.cargar_modelo(tts.MODELO_BASE)
    prompt = base.create_voice_clone_prompt(ref_audio=(ref, sr), ref_text=REF_TEXT)
    wavs, sr = base.generate_voice_clone(
        text=texto_completo,
        language=voz_cfg["language"],
        voice_clone_prompt=prompt,
        max_new_tokens=8192,
    )
    tts.liberar(base)

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
    return f"Voz generada (narración continua): {dur:.1f}s (atempo {atempo})"
