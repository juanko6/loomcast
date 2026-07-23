"""Etapa 4 — VOZ: clona la voz del banco elegida y narra el guion completo.

El proyecto debe tener una voz seleccionada (proyecto.voz → banco de voces).
El modelo Base convierte su clip de referencia en un voice_clone_prompt y
sintetiza el guion COMPLETO en una sola pasada: la narración fluye como
relato continuo y las pausas las da la puntuación. Después atempo →
voz.wav / voz.mp3.
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


def generar_voz(proyecto_id: int) -> str:
    import soundfile as sf

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        if not p.voz:
            raise ValueError("Selecciona una voz del banco antes de generar la voz")
        voz = voces_repo.por_slug(s, p.voz)
        if voz is None or voz.estado != "lista":
            raise ValueError(f"La voz '{p.voz}' no está disponible")
        slug, plantilla = p.slug, p.plantilla
        voz_slug, ref_text = voz.slug, voz.ref_text

    ref_path = voces_repo.ruta_ref(voz_slug)
    if not ref_path.exists():
        raise ValueError(f"Falta el clip de referencia de la voz '{voz_slug}'")

    g = json.loads(guion_row.contenido)
    texto_completo = guiones_repo.texto_narrado(g)
    ritmo = plantillas_repo.cargar(plantilla)["ritmo"]

    base_dir = PROYECTOS_DIR / slug
    base_dir.mkdir(parents=True, exist_ok=True)

    ref, ref_sr = sf.read(ref_path, dtype="float32")

    base = tts.cargar_modelo(tts.MODELO_BASE)
    prompt = base.create_voice_clone_prompt(ref_audio=(ref, ref_sr), ref_text=ref_text)
    wavs, sr = base.generate_voice_clone(
        text=texto_completo,
        language="Spanish",
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
    return f"Voz '{voz_slug}' narrando: {dur:.1f}s (atempo {atempo})"
