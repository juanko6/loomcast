"""Custom node de ComfyUI que esquiva el bug del escalado `area` en Metal.

EL BUG
`interpolate(mode="area")` es un adaptive average pooling, y la implementación
de MPS solo cubre el caso en que el tamaño de entrada es divisible por el de
salida. Con cualquier otro par revienta con:

    Adaptive pool MPS: input sizes must be divisible by output sizes.
    Non-divisible input sizes are not implemented on MPS device yet. For now,
    you can manually transfer tensor to cpu in this case.

Medido en PyTorch puro (torch 2.14.0.dev20260630, M3 Max):

    1024 -> 512 (divisible) ......... OK
    1024 -> 384 (no divisible) ...... RuntimeError

QUÉ ROMPE
Los nodos de Qwen-Image-Edit escalan las referencias con `area` a dos tamaños
(`comfy_extras/nodes_qwen.py`): ~384x384 para el encoder visual y ~1024x1024
para el latente de referencia. El segundo suele salvarse porque el redondeo a
múltiplos de 8 lo deja en el tamaño que ya traía la imagen (escalado previo) y
la división es exacta; el primero casi nunca, porque 384 no divide a 1024. Por
eso Qwen-Image-Edit no podía usarse como motor de escenas de personaje en Mac y
había que ir con FLUX.2 Klein, que escala con lanczos.

EL ARREGLO
Justo el que sugiere el mensaje de PyTorch: hacer ESE interpolate en CPU y
devolver el resultado a MPS. No se cambia el filtro, así que la imagen sale
idéntica a la de cualquier otro backend — que es el motivo de no tirar por el
camino fácil de sustituir `area` por `bilinear`. El coste es mover un tensor
pequeño (una referencia de 1024x1024 son 12 MB) un par de veces por imagen,
nada al lado de los segundos que tarda un paso de difusión.

Solo se desvía lo que HOY revienta: `mode="area"`, tensor en MPS y tamaños no
divisibles. Cualquier otra combinación sigue yendo por el interpolate de
siempre, así que no hay forma de que esto cambie el comportamiento de un
modelo que ya funcionaba.

Se puede quitar borrando el enlace de custom_nodes/ y reiniciando ComfyUI.
"""
import logging

import torch

_interpolate_original = torch.nn.functional.interpolate


def _destino(entrada, size, scale_factor):
    """Tamaño espacial de salida, o None si no se puede saber de antemano."""
    espaciales = entrada.dim() - 2
    if size is not None:
        if isinstance(size, int):
            return (size,) * espaciales
        return tuple(size)
    if scale_factor is not None:
        factores = (
            (scale_factor,) * espaciales
            if isinstance(scale_factor, (int, float))
            else tuple(scale_factor)
        )
        # interpolate trunca, no redondea.
        return tuple(int(d * f) for d, f in zip(entrada.shape[2:], factores))
    return None


def _necesita_cpu(entrada, destino):
    """¿Es este el caso que el adaptive pool de MPS no sabe hacer?"""
    if destino is None:
        return False
    for dentro, dfuera in zip(entrada.shape[2:], destino):
        if dfuera <= 0 or dentro % dfuera != 0:
            return True
    return False


def _interpolate_seguro(
    input,
    size=None,
    scale_factor=None,
    mode="nearest",
    align_corners=None,
    recompute_scale_factor=None,
    antialias=False,
):
    if mode == "area" and input.device.type == "mps":
        destino = _destino(input, size, scale_factor)
        if _necesita_cpu(input, destino):
            # adaptive_avg_pool2d en CPU no cubre media precisión, y de todas
            # formas el promediado conviene hacerlo en fp32.
            origen = input.dtype
            calculo = torch.float32 if origen in (torch.float16, torch.bfloat16) else origen
            salida = _interpolate_original(
                input.detach().to("cpu", dtype=calculo),
                size=destino,
                mode="area",
            )
            return salida.to(input.device, dtype=origen)

    return _interpolate_original(
        input,
        size=size,
        scale_factor=scale_factor,
        mode=mode,
        align_corners=align_corners,
        recompute_scale_factor=recompute_scale_factor,
        antialias=antialias,
    )


torch.nn.functional.interpolate = _interpolate_seguro
logging.info(
    "[loomcast] Parche del escalado area en MPS activo "
    "(permite Qwen-Image-Edit con imágenes de referencia)."
)
