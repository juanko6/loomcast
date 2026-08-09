"""Custom node de ComfyUI que esquiva el bug de torch.multinomial en Metal.

EL BUG
`torch.multinomial` sobre MPS devuelve índices fuera del soporte cuando la
distribución es grande. No es un problema de precisión ni de cómo se enmascara:
es el TAMAÑO. Comprobado en PyTorch puro (torch 2.14.0.dev, M3 Max), muestreando
un vocabulario de 217k con solo 64k valores no nulos:

    enmascarado con finfo.min ....... 4 de 500 muestras fuera de rango
    enmascarado con -inf en fp32 .... 4 de 500
    muestreando solo el tramo de 64k. 0 de 500

QUÉ ROMPE
ACE-Step 1.5 planifica la canción con un LM que muestrea sobre el vocabulario
entero de Qwen (~217k) enmascarando todo lo que no sean códigos de audio. Cada
token corrupto se convierte en un código inválido:

  - En pistas de más de ~33 s el índice se sale del rango y TUMBA la generación
    con un "index -33790 is out of bounds for dimension with size 64000",
    señalando a un nodo que no tiene la culpa (los errores de MPS son
    asíncronos, así que el traceback apunta a donde se vació la cola).
  - En pistas cortas suele caer dentro del rango y degrada el plan EN SILENCIO.

EL ARREGLO
Muestrear solo el soporte real. Los valores enmascarados salen de la softmax
como cero exacto (finfo.min / temperature desborda a -inf), así que `nonzero`
recupera exactamente el tramo válido, se muestrea ahí y se traduce el índice de
vuelta. Estadísticamente es la misma distribución; lo único que cambia es el
tamaño del tensor que ve la operación rota.

El parche se activa solo mientras corre el muestreo del LM de ACE-Step, no de
forma global, y solo sobre MPS: cualquier otro modelo y cualquier otro backend
siguen usando el torch.multinomial de siempre. ComfyUI ejecuta los prompts en
serie, así que intercambiar el símbolo durante la llamada es seguro.

Se puede quitar borrando el enlace de custom_nodes/ y reiniciando ComfyUI.
"""
import logging

import torch

import comfy.text_encoders.ace15 as ace15

# Por encima de esto es donde la operación empieza a fallar; el soporte real de
# ACE-Step son 64k, así que el margen es amplio por los dos lados.
LIMITE = 100_000

_multinomial_original = torch.multinomial
_muestreo_original = ace15.sample_manual_loop_no_classes


def _multinomial_seguro(probs, num_samples=1, replacement=False, *, generator=None, out=None):
    es_grande = probs.device.type == "mps" and probs.dim() == 2 and probs.shape[-1] > LIMITE
    if es_grande and probs.shape[0] == 1:
        soporte = probs[0].nonzero(as_tuple=True)[0]
        if 0 < soporte.numel() <= LIMITE:
            elegido = _multinomial_original(
                probs[:, soporte], num_samples, replacement, generator=generator
            )
            return soporte[elegido]
    return _multinomial_original(probs, num_samples, replacement, generator=generator)


def _muestreo_parcheado(*args, **kwargs):
    torch.multinomial = _multinomial_seguro
    try:
        return _muestreo_original(*args, **kwargs)
    finally:
        torch.multinomial = _multinomial_original


ace15.sample_manual_loop_no_classes = _muestreo_parcheado
logging.info(
    "[loomcast] Parche de torch.multinomial en MPS activo para ACE-Step 1.5 "
    "(permite lm_temperature > 0 en GPU sin el tope de ~33 s)."
)

# ComfyUI espera estas dos en todo paquete de custom_nodes; aquí no aportamos
# nodos, solo el parche que se aplica al importar.
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
