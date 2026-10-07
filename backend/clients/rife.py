"""Adaptador de RIFE (rife-ncnn-vulkan): interpola un clip a más fps.

Corre en GPU vía Vulkan/MoltenVK. Extrae los cuadros del clip, genera los
intermedios con RIFE y rearma el video a los fps finales.
"""
import tempfile
from pathlib import Path

from .. import procesos
from ..config import RIFE_BIN, RIFE_MODELO, ROOT


class RifeError(RuntimeError):
    pass


def _correr(cmd: list[str], timeout: float, que: str, **kw):
    """Proceso con tope de tiempo; un cuelgue sube como RifeError."""
    try:
        return procesos.ejecutar(cmd, timeout=timeout, que=que, **kw)
    except procesos.ProcesoTimeout as e:
        raise RifeError(str(e)) from e


def interpolar(
    entrada: Path,
    salida: Path,
    fps_origen: int,
    fps_final: int,
    frames: int | None = None,
) -> None:
    """Interpola `entrada` a `fps_final` y la escribe en `salida`.

    Por defecto multiplica los cuadros por fps_final/fps_origen, lo que asume
    que el clip ya dura lo que tiene que durar. Si se pasa `frames`, RIFE
    genera exactamente esa cantidad: sirve para clips i2v cortos que hay que
    estirar hasta la duración de su escena, donde el factor por fps dejaría
    demasiados cuadros repetidos.
    """
    bin_path = ROOT / RIFE_BIN
    if not bin_path.exists():
        raise RifeError(
            f"No se encontró rife-ncnn-vulkan en {bin_path}. "
            "Revisa la ruta en config.toml [rife].bin"
        )
    modelo_dir = bin_path.parent / RIFE_MODELO
    if not modelo_dir.exists():
        raise RifeError(f"No se encontró el modelo RIFE en {modelo_dir}")

    with tempfile.TemporaryDirectory() as tmp:
        din, dout = Path(tmp) / "in", Path(tmp) / "out"
        din.mkdir()
        dout.mkdir()

        _correr(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(entrada),
             str(din / "%08d.png")],
            procesos.CORTO_S, "ffmpeg (extraer cuadros)", check=True,
        )
        n_in = len(list(din.glob("*.png")))
        if n_in == 0:
            raise RifeError("ffmpeg no extrajo cuadros del clip i2v")

        n_out = frames if frames else n_in * max(2, round(fps_final / fps_origen))
        n_out = max(n_out, n_in)

        r = _correr(
            [str(bin_path), "-i", str(din), "-o", str(dout),
             "-m", str(modelo_dir), "-n", str(n_out), "-f", "%08d.png"],
            procesos.RIFE_S, "RIFE", capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RifeError(f"RIFE falló: {r.stderr[-400:]}")

        _correr(
            ["ffmpeg", "-loglevel", "error", "-y",
             "-framerate", str(fps_final), "-i", str(dout / "%08d.png"),
             "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(salida)],
            procesos.CLIP_S, "ffmpeg (rearmar el clip)", check=True,
        )
