# Fase 0 — Resultados de validación (2026-07-18)

Hardware: M3 Max, 48 GB unificada, macOS. ComfyUI 0.27.0 (MPS), Python 3.12.

## Veredicto: ✅ todo el pipeline es viable 100% local en esta Mac

| Componente | Prueba | Resultado |
|---|---|---|
| **Z-Image-Turbo bf16** (ComfyUI/MPS) | 768×1344, 8 pasos, res_multistep | **~47 s/imagen** en caliente (63 s la primera con carga). Calidad excelente, sin artefactos. El text encoder `qwen_3_4b_fp4_mixed` funciona bien en MPS. |
| **Qwen3-TTS 1.7B VoiceDesign** (MPS) | Párrafo español 14.7 s, voz diseñada por descripción | **RTF 1.54** (22.6 s de generación). Carga en 6.7 s. Lee números en dígitos correctamente en español. Audio: `tts_es_prueba.wav` (calidad pendiente de juicio del usuario). |
| **mlx-whisper large-v3-turbo** | Transcripción del audio TTS, `word_timestamps=True` | **3.2 s** para 14.7 s de audio. Transcripción 100 % correcta; devuelve números como dígitos (ideal para subtítulos compactos). |
| **Real-ESRGAN x4plus** (ComfyUI) | 768×1344 → 3072×5376 | **7.1 s/imagen** |
| **RIFE** (rife-ncnn-vulkan, GPU Vulkan/MoltenVK) | 48→96 cuadros @768×1344, modelo v4.6 | **8.1 s** (~0.17 s/cuadro generado). Binario corre nativo en macOS, trae modelos hasta v4.6. |
| **Ken Burns** (ffmpeg zoompan) | 48 cuadros 24 fps desde imagen | **1.3 s** |
| **Gestión de memoria** | `POST /free` a ComfyUI | Libera el stack Z-Image (~20 GB): RAM libre pasó de 12.7 → 33.1 GB. Mecanismo confirmado para alternar servicios. |

## Consumo de memoria observado

- ComfyUI + Z-Image cargado: **~20 GB** (se libera con `POST /free {"unload_models":true,"free_memory":true}`)
- Qwen3-TTS 1.7B: **~5 GB** (bf16 + tokenizer)
- mlx-whisper turbo: **~2 GB**
- Con 48 GB, TTS + Whisper + LLM (llama.cpp) pueden convivir; Z-Image conviene cargarlo solo durante la etapa de imágenes.

## Cambios de diseño derivados de las mediciones

1. **Reordenar el pipeline visual**: `imagen → ESRGAN → Ken Burns a 1080×1920 → RIFE`, en lugar de reescalar los clips cuadro a cuadro. Reescalar 12 imágenes cuesta ~85 s; reescalar ~1200 cuadros de video costaría horas. El clip Ken Burns se genera directamente a resolución final desde la imagen ya reescalada.
2. **Voz por proyecto con "Design then Clone"**: VoiceDesign genera un clip de referencia según la descripción de la plantilla → `create_voice_clone_prompt` lo convierte en voz reutilizable → `generate_voice_clone` sintetiza todas las frases con voz consistente. Voz distinta por video, consistente dentro del video.
3. **RIFE con modelo v4.6** (`-n` acepta conteo arbitrario de cuadros).

## Estimación de tiempo total por video (45 s, ~12 escenas)

| Etapa | Tiempo estimado |
|---|---|
| Ideas + guion + metadatos (llama.cpp) | ~2 min |
| Voz (TTS, RTF 1.5 sobre ~45 s) | ~1.5 min |
| Subtítulos (Whisper) | ~5 s |
| Prompts de escenas (llama.cpp) | ~30 s |
| Imágenes (12 × 47 s) | ~9.5 min |
| ESRGAN (12 × 7 s) | ~1.5 min |
| Ken Burns + RIFE + armado | ~4 min |
| **Total** | **~15–20 min por video** |

## Artefactos de la fase

- `test_zimage.py`, `test_qwen_tts.py`, `test_whisper.py`, `test_esrgan.py`, `test_rife.sh` — scripts reutilizables
- `../workflows/z_image_turbo_api.json` — workflow API de Z-Image 9:16 (base para producción)
- `tts_es_prueba.wav` — muestra de voz en español
- `rife_test/clip_48fps.mp4` — clip Ken Burns interpolado de muestra
- Imágenes de prueba en `~/Documents/ComfyUI/ComfyUI/output/loomcast_fase0*.png`
