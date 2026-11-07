"""Escalado x4 de una carpeta de cuadros, para llevar una imagen animada a 2K/4K.

Dos caminos, elegidos en config.toml [animada].escalador:

  - "ncnn": `realesrgan-ncnn-vulkan` (GPU por Vulkan/MoltenVK, como RIFE). Hace
    la carpeta entera de una pasada, sin ir y venir por HTTP, y con
    `realesr-animevideov3` está pensado para vídeo: menos parpadeo entre cuadros.
  - "comfy": Real-ESRGAN x4plus dentro de ComfyUI, un prompt por cuadro. No
    necesita nada más instalado, pero es el modelo de fotos.
"""
from pathlib import Path

from .. import procesos
from ..config import (
    ANIMADA_ESCALADOR,
    ANIMADA_ESCALADOR_BIN,
    ANIMADA_ESCALADOR_MODELO,
    ROOT,
)
from . import comfy


class EscaladorError(RuntimeError):
    pass


def escalar_cuadros(entrada: Path, salida: Path, que_hacer=None) -> None:
    """Escala x4 todos los PNG de `entrada` y los deja con el mismo nombre en
    `salida`. `que_hacer(i, n)` se llama antes de cada cuadro en el camino de
    ComfyUI, que es el lento: sirve para el progreso y para poder parar."""
    cuadros = sorted(entrada.glob("*.png"))
    if not cuadros:
        raise EscaladorError(f"No hay cuadros que escalar en {entrada}")
    salida.mkdir(parents=True, exist_ok=True)
    if ANIMADA_ESCALADOR == "ncnn":
        _ncnn(entrada, salida, len(cuadros))
    elif ANIMADA_ESCALADOR == "comfy":
        for i, c in enumerate(cuadros):
            if que_hacer:
                que_hacer(i, len(cuadros))
            comfy.upscale_imagen(c, salida / c.name)
    else:
        raise EscaladorError(
            f"[animada].escalador = '{ANIMADA_ESCALADOR}' no existe: usa 'ncnn' o 'comfy'"
        )


def _ncnn(entrada: Path, salida: Path, n: int) -> None:
    bin_path = ROOT / ANIMADA_ESCALADOR_BIN
    if not bin_path.exists():
        raise EscaladorError(
            f"No se encontró realesrgan-ncnn-vulkan en {bin_path}. "
            "Revisa config.toml [animada].escalador_bin"
        )
    try:
        r = procesos.ejecutar(
            [str(bin_path), "-i", str(entrada), "-o", str(salida),
             "-n", ANIMADA_ESCALADOR_MODELO, "-s", "4", "-f", "png",
             "-m", str(bin_path.parent / "models")],
            timeout=procesos.RIFE_S, que="Real-ESRGAN",
            capture_output=True, text=True,
        )
    except procesos.ProcesoTimeout as e:
        raise EscaladorError(str(e)) from e
    if r.returncode != 0:
        raise EscaladorError(f"Real-ESRGAN falló: {r.stderr[-400:]}")
    hechos = len(list(salida.glob("*.png")))
    if hechos != n:
        raise EscaladorError(f"Real-ESRGAN dejó {hechos} cuadros de {n}")
