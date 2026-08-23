"""Adaptador de transcripción (STT): audio → texto y timestamps por palabra.

Lo usan la etapa de subtítulos (que necesita las palabras para el SRT y para
`palabras.json`, insumo del reparto de escenas) y el clonado de voz (que solo
necesita el texto para el ref_text del ICL).

Detrás va faster-whisper (CTranslate2), que corre igual en Mac (CPU) y en
Linux con CUDA. Antes esto era mlx-whisper, que solo existe en Apple Silicon y
ataba todo el backend a Mac; el motor queda escondido aquí para que cambiarlo
—o volver a tener varios— no se note en las etapas.

El modelo se carga una vez y se reutiliza: cargarlo cuesta más que transcribir
los 30-60 s de una voz.
"""
import threading
from pathlib import Path

from ..config import STT_COMPUTE_TYPE, STT_DISPOSITIVO, STT_IDIOMA, STT_MODELO

_modelo = None
_lock = threading.Lock()


def _cargar():
    """Devuelve el WhisperModel, cargándolo la primera vez.

    Con lock porque la cola de jobs corre en su propio hilo y el arranque del
    servidor podría pedir una transcripción a la vez que otra etapa.
    """
    global _modelo
    with _lock:
        if _modelo is None:
            from faster_whisper import WhisperModel

            _modelo = WhisperModel(
                STT_MODELO,
                device=STT_DISPOSITIVO,
                compute_type=STT_COMPUTE_TYPE,
            )
        return _modelo


def transcribir(audio: Path, *, palabras: bool = False) -> dict:
    """Transcribe `audio` y devuelve {"texto": str, "palabras": [...]}.

    Con `palabras=True` cada elemento de "palabras" es
    {"word": str, "start": float, "end": float} — la misma forma que consumían
    las etapas cuando esto era mlx-whisper, para que el SRT y palabras.json no
    se enteren del cambio de motor. Sin `palabras`, la lista viene vacía y se
    ahorra el alineado por atención, que no es gratis.
    """
    modelo = _cargar()
    # `segments` es un generador perezoso: la transcripción no ocurre hasta que
    # se recorre. Materializarla aquí es lo que hace que los errores salgan en
    # esta llamada y no más tarde, en medio de la etapa que la pidió.
    segmentos, _info = modelo.transcribe(
        str(audio), language=STT_IDIOMA, word_timestamps=palabras
    )
    segmentos = list(segmentos)

    texto = "".join(s.text for s in segmentos).strip()
    sueltas = [
        {"word": w.word, "start": float(w.start), "end": float(w.end)}
        for s in segmentos
        for w in (s.words or [])
    ] if palabras else []
    return {"texto": texto, "palabras": sueltas}


def liberar() -> None:
    """Suelta el modelo. La etapa de voz y ComfyUI se pelean por la memoria
    unificada, así que conviene poder devolver estos ~1,5 GB."""
    global _modelo
    with _lock:
        _modelo = None
