"""Adaptador de Qwen3-TTS: carga y liberación de modelos en MPS."""
import gc

MODELO_DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
MODELO_BASE = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"


def cargar_modelo(repo: str):
    import torch
    from qwen_tts import Qwen3TTSModel

    return Qwen3TTSModel.from_pretrained(
        repo, device_map="mps", dtype=torch.bfloat16, attn_implementation="sdpa"
    )


def liberar(modelo) -> None:
    import torch

    del modelo
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
