"""Adaptador de RIFE (rife-ncnn-vulkan): interpola un clip a más fps.

Corre en GPU vía Vulkan/MoltenVK. Extrae los cuadros del clip, genera los
intermedios con RIFE y rearma el video a los fps finales.
"""
import subprocess
import tempfile
from pathlib import Path

from ..config import RIFE_BIN, RIFE_MODELO, ROOT


class RifeError(RuntimeError):
    pass


def interpolar(entrada: Path, salida: Path, fps_origen: int, fps_final: int) -> None:
    bin_path = ROOT / RIFE_BIN
    if not bin_path.exists():
        raise RifeError(
            f"No se encontró rife-ncnn-vulkan en {bin_path}. "
            "Revisa la ruta en config.toml [rife].bin"
        )
    modelo_dir = bin_path.parent / RIFE_MODELO
    if not modelo_dir.exists():
        raise RifeError(f"No se encontró el modelo RIFE en {modelo_dir}")

    factor = max(2, round(fps_final / fps_origen))
    with tempfile.TemporaryDirectory() as tmp:
        din, dout = Path(tmp) / "in", Path(tmp) / "out"
        din.mkdir()
        dout.mkdir()

        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(entrada),
             str(din / "%08d.png")],
            check=True,
        )
        n_in = len(list(din.glob("*.png")))
        if n_in == 0:
            raise RifeError("ffmpeg no extrajo cuadros del clip i2v")

        r = subprocess.run(
            [str(bin_path), "-i", str(din), "-o", str(dout),
             "-m", str(modelo_dir), "-n", str(n_in * factor), "-f", "%08d.png"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RifeError(f"RIFE falló: {r.stderr[-400:]}")

        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y",
             "-framerate", str(fps_final), "-i", str(dout / "%08d.png"),
             "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(salida)],
            check=True,
        )
