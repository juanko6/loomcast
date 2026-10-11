"""Custom node de ComfyUI que dequantiza los parámetros sueltos que un GGUF
traiga cuantizados por error.

El GGUF de molbal cuantizó `keyframes_abs_pos_embedding` a Q4_0, y eso no es
una matriz de pesos sino un nn.Parameter de 4096 floats. En Q4_0 ocupa 2304
bytes, así que ComfyUI aborta:

    While copying the parameter named "keyframes_abs_pos_embedding" ... model
    are torch.Size([1, 4096]) and ... checkpoint are torch.Size([1, 2304])

ComfyUI-GGUF ya hace justo esto para el caso BF16 ("1D tensors shouldn't be
quantized", loader.py:142), pero la condición pide len(shape) <= 1 y aquí la
forma es [1, 4096].

Dos detalles que no se ven a simple vista:
  - Hay DOS custom nodes de GGUF instalados (ComfyUI-GGUF de city96 y `gguf` de
    calcuis) y ambos exponen un `gguf_sd_loader`. El que carga el unet es el de
    city96, así que hay que mirar de qué fichero viene cada uno.
  - `nodes.py` hace `from .loader import gguf_sd_loader`, o sea que tiene su
    propia referencia: parchear solo `loader` no sirve de nada.
  - La función devuelve `(state_dict, extra)`, no un state_dict.

Si algún día el fichero se vuelve a convertir bien, o se pasa al checkpoint
oficial en int8, esto deja de hacer falta: el parche solo actúa cuando encuentra
un parámetro suelto en un tipo que no es F32/F16, así que con un GGUF correcto
no toca nada.

Se instala con `python scripts/instalar_parches.py`, que lo enlaza en
custom_nodes/ para que el código siga viviendo versionado aquí.
"""
import logging
import sys

import torch

SOSPECHOSOS = ("keyframes_abs_pos_embedding", "scale_shift_table", "pos_embedding")


def _es_de_city96(mod) -> bool:
    return "ComfyUI-GGUF" in (getattr(mod, "__file__", "") or "")


_loader = next(
    (m for m in list(sys.modules.values())
     if m is not None and _es_de_city96(m)
     and hasattr(m, "gguf_sd_loader") and hasattr(m, "dequantize_tensor")),
    None,
)

if _loader is None:
    logging.warning("[loomcast] No encuentro el loader de ComfyUI-GGUF; el parche de LTX-2.5 no se aplica.")
else:
    _original = _loader.gguf_sd_loader
    _dequantizar = _loader.dequantize_tensor

    def _reparar(sd):
        for clave, valor in list(sd.items()):
            if not any(s in clave for s in SOSPECHOSOS):
                continue
            tipo = getattr(valor, "tensor_type", None)
            # F32/F16 llegan bien; cualquier otro tipo en un parámetro suelto
            # es el fallo de conversión.
            if tipo is not None and getattr(tipo, "name", "") not in ("F32", "F16"):
                sd[clave] = _dequantizar(valor, dtype=torch.float32)
                logging.info(
                    f"[loomcast] GGUF: {clave} venía en {tipo.name} siendo un "
                    "parámetro suelto; dequantizado a F32."
                )
        return sd

    def _loader_reparado(*args, **kwargs):
        salida = _original(*args, **kwargs)
        # Devuelve (state_dict, extra) en las versiones nuevas y el dict a secas
        # en las viejas.
        if isinstance(salida, tuple):
            return (_reparar(salida[0]),) + salida[1:]
        return _reparar(salida)

    tocados = [
        m.__name__ for m in list(sys.modules.values())
        if m is not None and getattr(m, "gguf_sd_loader", None) is _original
    ]
    for nombre in tocados:
        sys.modules[nombre].gguf_sd_loader = _loader_reparado
    logging.info(
        f"[loomcast] Parche del GGUF de LTX-2.5 activo en: {', '.join(tocados) or 'ninguno'}"
    )

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
