"""Adaptador de Qwen3-TTS: carga y liberación de modelos en MPS."""
import gc

MODELO_DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
MODELO_BASE = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"


def cargar_modelo(repo: str):
    """Carga un Qwen3-TTS en MPS.

    **fp16 y no bf16**: el M3 no acelera bfloat16 por hardware y lo emula, con
    el mismo efecto que ya se vio en ComfyUI. Medido narrando 106 palabras: en
    bf16 la generación mandó 18 GB al swap y en fp16 se queda en 4,2, con el
    mismo audio y algo menos de tiempo.

    Antes de cargar se suelta whisper: la etapa que lo cargó ya terminó (es la
    de subtítulos, que va *después* de la voz) y sus ~1,5 GB se quedaban dentro
    porque `stt.liberar()` existía y no lo llamaba nadie. Los dos modelos no se
    necesitan nunca a la vez.
    """
    import torch
    from qwen_tts import Qwen3TTSModel

    from . import stt

    stt.liberar()
    return Qwen3TTSModel.from_pretrained(
        repo, device_map="mps", dtype=torch.float16, attn_implementation="sdpa"
    )


def tope_tokens(texto: str) -> int:
    """Cuántos tokens de audio pedirle como mucho para narrar `texto`.

    El modelo entrega a 12 Hz y gasta unos 6 tokens por palabra (medido: 620
    tokens para 106 palabras, 52 s de audio), así que con 12 por palabra sobra
    el doble. El mínimo cubre los textos muy cortos.

    **No lo pongas aquí esperando ahorrar memoria.** Se midió el mismo texto con
    768, 1024 y 1428 y el swap salió 5,7 / 8,7 / 6,6 GB: ruido, no curva. El
    tope solo evita pedir a ciegas diez veces lo necesario.

    Ya se sabe por qué no era curva: el pico no lo marcaba cuántos tokens se
    pedían sino que el asignador de MPS no soltaba lo cacheado entre paso y
    paso (ver `VOZ_MPS_TOPE` en config.py, que es lo que lo arregló: pico de
    53,1 a 15,6 GiB narrando el mismo guion). Lo otro que movió la aguja fue
    pasar de bf16 a fp16 (ver `cargar_modelo`).
    """
    return max(1024, len(texto.split()) * 12)


def liberar() -> None:
    """Recoge lo que el TTS dejó en MPS.

    **Suelta tu referencia al modelo antes de llamar** (`modelo = None`). No
    recibe el modelo a propósito: la versión que lo recibía hacía `del modelo`
    sobre su propio parámetro, que borra el nombre de *esta* función y deja
    intacto el del que llama, así que el `gc.collect()` corría con el modelo
    todavía vivo y no liberaba nada. Peor: en el bucle por modelos de `voz.py`
    el siguiente `cargar_modelo` se construía con el anterior aún referenciado,
    o sea los dos Qwen3-TTS en memoria a la vez.
    """
    import torch

    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
