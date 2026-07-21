"""Argumentos de codificación de video, según config.toml [video].

El modo hardware (h264_videotoolbox) descarga la codificación en el motor de
medios de Apple: muy poca CPU y más rápido. El software (libx264) da la mejor
calidad por bit a costa de CPU. Los filtros (zoompan, overlay) siguen en CPU
en ambos casos: no son acelerables por hardware.
"""
from ...config import VIDEO_BITRATE_MBPS, VIDEO_CRF, VIDEO_ENCODER


def args_video() -> list[str]:
    if VIDEO_ENCODER == "software":
        return ["-c:v", "libx264", "-preset", "medium", "-crf", str(VIDEO_CRF),
                "-pix_fmt", "yuv420p"]
    # hardware (por defecto): VideoToolbox con fallback a software si el motor
    # está ocupado. Usa bitrate objetivo porque no admite CRF.
    return ["-c:v", "h264_videotoolbox", "-b:v", f"{VIDEO_BITRATE_MBPS}M",
            "-allow_sw", "1", "-pix_fmt", "yuv420p"]
