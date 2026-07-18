# Loomcast

Generador automatizado de videos cortos (30–60 s, 9:16) para YouTube Shorts y TikTok, **100% con IA local** en Apple Silicon.

Tema → ideas → guion → metadatos → voz (Qwen3-TTS) → subtítulos (Whisper) → imágenes (Z-Image-Turbo vía ComfyUI) → upscale (Real-ESRGAN) → clips → interpolación (RIFE) → video final.

Ver [PLAN.md](PLAN.md) para la arquitectura completa y [fase0/RESULTADOS.md](fase0/RESULTADOS.md) para las mediciones de rendimiento.

## Requisitos

- macOS con Apple Silicon (desarrollado en M3 Max / 48 GB)
- Python 3.12
- [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) con un modelo instruct en español
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) con Z-Image-Turbo (bf16), VAE `ae.safetensors` y text encoder `qwen_3_4b`
- ffmpeg

## Arranque

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 1. llama-server corriendo (puerto en config.toml, por defecto 8001)
# 2. ComfyUI corriendo (por defecto 8188)

./.venv/bin/uvicorn backend.main:app --port 8700
# UI en http://127.0.0.1:8700
```

## Estado

- ✅ Fase 0 — validación del stack completo en local
- ✅ Fase 1 — núcleo de texto: ideas, selección, guion editable, metadatos (UI + jobs)
- ⬜ Fase 2 — voz y subtítulos
- ⬜ Fase 3 — escenas, imágenes y clips
- ⬜ Fase 4 — acabado (upscale, interpolación, armado)
