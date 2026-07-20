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

## Arquitectura del backend

Capas (de HTTP hacia abajo): `routers/` (controllers: validación y JSON, cero lógica) → `services/` (reglas de negocio; `services/pipeline/` son las etapas de generación) → `repositories/` (consultas a SQLite y carga de plantillas) → `models.py` (ORM + máquina de estados). Transversales: `clients/` (adaptadores a llama-server y Qwen3-TTS), `workers/queue.py` (cola de jobs en un hilo, uno a la vez, con encadenado y recuperación), `schemas.py` (contratos Pydantic de la API).

## Flujo de creación (UI)

Tema → ideas → seleccionar/aprobar → **1** guion (editar/regenerar) → **2** voz (elegir del banco o crear nueva → generar narración) → **3** metadatos → **4** escenas (generar prompts → editarlos → aceptar y generar imágenes) → **5** armar video final.

Puntos de revisión humana: selección de ideas, guion, elección de voz, y **prompts de escena antes de gastar GPU en las imágenes**.

## Banco de voces

Voces reutilizables generadas con Qwen3-TTS VoiceDesign, guardadas en `voces/<slug>/ref.wav`. Cada proyecto elige una; la narración se produce clonando ese clip. Sembrar 6 de arranque: `./.venv/bin/python scripts/sembrar_voces.py`. Crear más desde la UI describiendo cómo debe sonar.

## Estado

- ✅ Fase 0 — validación del stack completo en local
- ✅ Fase 1 — núcleo de texto: ideas, selección, guion editable, metadatos (UI + jobs)
- ✅ Fase 2 — voz (Qwen3-TTS design-then-clone, narración continua) y subtítulos (mlx-whisper, SRT en bloques de ≤3 palabras)
- ✅ Fase 3 — escenas (prompts visuales en inglés por segmento, **editables antes de generar**), imágenes (Z-Image vía ComfyUI) y **armado estático**: video completo con imágenes fijas, voz, subtítulos compuestos con Pillow y metadatos
- ✅ Banco de voces + flujo de creación por pasos con revisión humana
- ⬜ Fase 4 — movimiento (Ken Burns/i2v), upscale ESRGAN e interpolación RIFE
