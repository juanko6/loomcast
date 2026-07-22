"""Argumentos de codificación de video, según config.toml [video].

El modo hardware (h264_videotoolbox) descarga la codificación en el motor de
medios de Apple: muy poca CPU y más rápido. El software (libx264) da la mejor
calidad por bit a costa de CPU. Los filtros (zoompan, overlay) siguen en CPU
en ambos casos: no son acelerables por hardware.
"""
import subprocess
from datetime import datetime
from pathlib import Path

from ...config import VIDEO_BITRATE_MBPS, VIDEO_CRF, VIDEO_ENCODER


def archivar_final(base: Path) -> str | None:
    """Aparta el final.mp4 anterior antes de sobrescribirlo.

    Armar escribe siempre sobre el mismo nombre, así que sin esto cada montaje
    borraría el resultado del anterior sin posibilidad de recuperarlo. Devuelve
    el nombre de la versión archivada, o None si no había nada que guardar.
    """
    final = base / "final.mp4"
    if not final.exists():
        return None
    versiones = base / "versiones"
    versiones.mkdir(exist_ok=True)
    marca = datetime.fromtimestamp(final.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
    destino = versiones / f"final_{marca}.mp4"
    final.rename(destino)
    return destino.name


def duracion(archivo: Path) -> float:
    """Duración en segundos de un archivo de video o audio (0.0 si falla)."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(archivo)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or 0)


def args_video() -> list[str]:
    if VIDEO_ENCODER == "software":
        return ["-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF),
                "-pix_fmt", "yuv420p"]
    # hardware (por defecto): VideoToolbox con fallback a software si el motor
    # está ocupado. Usa bitrate objetivo porque no admite CRF.
    return ["-c:v", "h264_videotoolbox", "-b:v", f"{VIDEO_BITRATE_MBPS}M",
            "-allow_sw", "1", "-pix_fmt", "yuv420p"]
