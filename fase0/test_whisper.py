"""Fase 0: mlx-whisper large-v3-turbo — timestamps por palabra sobre el audio TTS."""
import time

import mlx_whisper

AUDIO = "/Users/juanko.dev/Documents/loomcast/fase0/tts_es_prueba.wav"

t0 = time.time()
result = mlx_whisper.transcribe(
    AUDIO,
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="es",
    word_timestamps=True,
)
dt = time.time() - t0

print(f"Transcripción en {dt:.1f}s\n")
print("Texto:", result["text"].strip(), "\n")
print("Palabras con timestamps:")
for seg in result["segments"]:
    for w in seg.get("words", []):
        print(f"  [{w['start']:6.2f} - {w['end']:6.2f}] {w['word']}")
