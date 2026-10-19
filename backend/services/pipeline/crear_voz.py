"""Jobs del banco de voces: genera el clip de referencia con VoiceDesign
(voz descrita) o lo clona de un audio real que aporta el usuario."""

import numpy as np

from ... import parada, procesos
from ...clients import stt, tts
from ...config import VOCES_DIR
from ...db import get_session
from ...repositories import voces as voces_repo

# El clon va mejor con una referencia corta y limpia; los refs de VoiceDesign
# rondan los 8 s a 24 kHz mono. Recortamos los clips largos a este máximo.
MAX_REF_S = 15
REF_SR = 24000


def crear_voz(voz_id: int) -> str:
    import soundfile as sf

    with get_session() as s:
        voz = voces_repo.obtener(s, voz_id)
        if voz is None:
            raise ValueError(f"Voz {voz_id} no existe")
        slug, instruct, ref_text = voz.slug, voz.instruct, voz.ref_text

    # La síntesis del clip de referencia tampoco se puede partir; esto es lo
    # último que se puede cortar.
    parada.comprobar("antes de sintetizar la voz de referencia")

    try:
        design = tts.cargar_modelo(tts.MODELO_DESIGN)
        wavs, sr = design.generate_voice_design(
            text=ref_text, language="Spanish", instruct=instruct
        )
        tts.liberar(design)
        ref = voces_repo.ruta_ref(slug)
        ref.parent.mkdir(parents=True, exist_ok=True)
        sf.write(ref, np.asarray(wavs[0], dtype=np.float32), sr)
    except Exception:
        with get_session() as s:
            voces_repo.obtener(s, voz_id).estado = "error"
            s.commit()
        raise

    with get_session() as s:
        voces_repo.obtener(s, voz_id).estado = "lista"
        s.commit()
    return f"Voz '{slug}' generada"


def clonar_voz(voz_id: int, inicio: float = 0.0, fin: float | None = None) -> str:
    """Clona la voz del clip real que dejó el usuario en voces/<slug>/origen.*:
    recorta el fragmento elegido [inicio, fin] (o los primeros MAX_REF_S s si no
    se indica), lo convierte a wav 24 kHz mono y lo transcribe para el ref_text.
    Sin VoiceDesign; la voz sale del propio audio."""
    with get_session() as s:
        voz = voces_repo.obtener(s, voz_id)
        if voz is None:
            raise ValueError(f"Voz {voz_id} no existe")
        slug = voz.slug

    base = VOCES_DIR / slug
    origenes = sorted(base.glob("origen.*"))
    if not origenes:
        raise ValueError(f"No hay audio de origen para clonar la voz '{slug}'")

    inicio = max(0.0, float(inicio or 0.0))
    dur = (float(fin) - inicio) if fin is not None else float(MAX_REF_S)
    dur = max(0.5, min(dur, MAX_REF_S))  # tope: refs cortos clonan igual y pesan menos

    try:
        ref = voces_repo.ruta_ref(slug)
        # El recorte va por procesos.py (se le puede mandar SIGTERM) y la
        # transcripción mira la bandera entre segmentos; el `except` de abajo
        # deja la voz en "error" también si se paró, que es lo honesto: no está
        # lista.
        procesos.ejecutar(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{inicio}",
             "-i", str(origenes[0]), "-t", f"{dur}",
             "-ac", "1", "-ar", str(REF_SR), str(ref)],
            timeout=procesos.CORTO_S, que="ffmpeg (recorte de la referencia)", check=True,
        )
        ref_text = stt.transcribir(ref)["texto"]
        if not ref_text:
            raise ValueError("La transcripción del clip quedó vacía")
    except Exception:
        with get_session() as s:
            voces_repo.obtener(s, voz_id).estado = "error"
            s.commit()
        raise

    with get_session() as s:
        v = voces_repo.obtener(s, voz_id)
        v.ref_text = ref_text
        v.estado = "lista"
        s.commit()
    return f"Voz '{slug}' clonada — ref_text: {ref_text[:60]}…"
