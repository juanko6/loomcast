"""Parches de Loomcast para los agujeros de PyTorch en Metal (MPS).

Cada módulo arregla un bug concreto y lleva en su docstring la medición que lo
demuestra y qué modelo rompía:

  - `multinomial`     torch.multinomial devuelve índices de probabilidad cero,
                      lo que tumba las pistas largas de ACE-Step 1.5.
  - `escalado_area`   interpolate(mode="area") solo admite tamaños divisibles,
                      lo que impedía usar Qwen-Image-Edit con referencias.

Los parches se aplican al importar el paquete, y son lo más estrechos posible:
solo entran en el caso exacto que falla y dejan intacto todo lo demás.

Se instala con `python scripts/instalar_parches.py`, que lo enlaza en
custom_nodes/ para que el código siga viviendo versionado aquí.
"""
from . import escalado_area, multinomial  # noqa: F401  (aplican al importarse)

# ComfyUI espera estas dos en todo paquete de custom_nodes; aquí no aportamos
# nodos, solo los parches.
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
