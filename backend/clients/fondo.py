"""Quitar el fondo de una imagen con rembg (u2net vía onnxruntime, en CPU).

No pasa por ComfyUI: es una segmentación ligera que no necesita la GPU ni el
pipeline de difusión. La sesión de rembg se crea una vez y se reutiliza (cargar
el modelo en cada llamada costaría segundos de más)."""
from pathlib import Path

from PIL import Image

_session = None


def _sesion():
    global _session
    if _session is None:
        from rembg import new_session

        _session = new_session("u2net")
    return _session


def quitar_fondo(origen: Path, destino: Path) -> None:
    """Deja el sujeto sobre fondo transparente y guarda un PNG RGBA en `destino`."""
    from rembg import remove

    with Image.open(origen) as im:
        recorte = remove(im.convert("RGB"), session=_sesion())
    recorte.save(destino, "PNG")
