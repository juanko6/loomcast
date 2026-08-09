"""Custom node de ComfyUI que esquiva el bug de torch.multinomial en Metal.

EL BUG
`torch.multinomial` sobre MPS devuelve a veces índices cuya probabilidad es
exactamente 0.0. Lo que lo dispara no es el tamaño del tensor sino la presencia
de entradas a cero, y la tasa crece con cuántas haya. Medido en PyTorch puro
(torch 2.14.0.dev20260630, M3 Max), con 217000 entradas y 2000 muestras por fila:

    sin ceros ....................... 0 de 2000
    117000 ceros .................... 2 de 2000
    153000 ceros .................... 6 de 2000
    216000 ceros ................... 10 de 2000

Tampoco es precisión: da igual enmascarar con finfo.min que con -inf en fp32.

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
Quitar los ceros antes de muestrear. Los valores enmascarados salen de la
softmax como cero exacto (finfo.min / temperature desborda a -inf), así que
`nonzero` recupera el soporte real, se muestrea ahí y se traduce el índice de
vuelta. Estadísticamente es la misma distribución; lo que desaparece es
justamente lo que dispara el fallo.

El parche se activa solo mientras corre el muestreo del LM de ACE-Step, no de
forma global, y solo sobre MPS: cualquier otro modelo y cualquier otro backend
siguen usando el torch.multinomial de siempre. ComfyUI ejecuta los prompts en
serie, así que intercambiar el símbolo durante la llamada es seguro.

Se puede quitar borrando el enlace de custom_nodes/ y reiniciando ComfyUI.
"""
import logging

import torch

import comfy.text_encoders.ace15 as ace15

# Por debajo de esto no compensa el coste del nonzero(), y el fallo solo se ha
# visto con distribuciones de vocabulario (decenas de miles de entradas).
MINIMO = 1024

_multinomial_original = torch.multinomial
_muestreo_original = ace15.sample_manual_loop_no_classes


def _multinomial_seguro(probs, num_samples=1, replacement=False, *, generator=None, out=None):
    aplica = (
        probs.device.type == "mps"
        and probs.dim() == 2
        and probs.shape[0] == 1
        and probs.shape[-1] > MINIMO
    )
    if aplica:
        soporte = probs[0].nonzero(as_tuple=True)[0]
        # Solo si hay ceros que quitar: sin ellos el fallo no se da y no hay
        # motivo para tocar nada.
        if 0 < soporte.numel() < probs.shape[-1]:
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
