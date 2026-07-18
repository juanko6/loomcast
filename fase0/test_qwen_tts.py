"""Fase 0: Qwen3-TTS VoiceDesign en español sobre MPS — calidad, velocidad y RTF."""
import time

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

TEXT = (
    "¿Sabías que el ochenta por ciento del oro del planeta sigue enterrado? "
    "En 1898, tres mineros encontraron una pepita de 72 kilos. "
    "Pero lo más increíble no fue el hallazgo, sino lo que hicieron después."
)
INSTRUCT = (
    "Voz masculina grave de narrador de documental en español, tono misterioso "
    "y envolvente, ritmo pausado pero con energía, dicción clara."
)

t0 = time.time()
model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    device_map="mps",
    dtype=torch.bfloat16,
    attn_implementation="sdpa",
)
print(f"Carga del modelo: {time.time() - t0:.1f}s")

t0 = time.time()
wavs, sr = model.generate_voice_design(text=TEXT, language="Spanish", instruct=INSTRUCT)
gen = time.time() - t0

audio_s = len(wavs[0]) / sr
sf.write("/Users/juanko.dev/Documents/loomcast/fase0/tts_es_prueba.wav", wavs[0], sr)
print(f"Generación: {gen:.1f}s | audio: {audio_s:.1f}s | RTF: {gen / audio_s:.2f}")
print("Guardado en fase0/tts_es_prueba.wav")
