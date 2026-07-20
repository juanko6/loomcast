"""Job del banco de voces: genera el clip de referencia con VoiceDesign."""
import numpy as np

from ...clients import tts
from ...db import get_session
from ...repositories import voces as voces_repo


def crear_voz(voz_id: int) -> str:
    import soundfile as sf

    with get_session() as s:
        voz = voces_repo.obtener(s, voz_id)
        if voz is None:
            raise ValueError(f"Voz {voz_id} no existe")
        slug, instruct, ref_text = voz.slug, voz.instruct, voz.ref_text

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
