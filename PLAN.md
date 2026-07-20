# Loomcast — Plan de proyecto

Generador automatizado de videos cortos (30–60 s, formato vertical 9:16) para YouTube Shorts y TikTok, **100% con IA local**.

> Estado: **Fase 2 completada** (2026-07-20) — voz con Qwen3-TTS (design→clone por proyecto, síntesis por frase en lote, atempo 1.05) y subtítulos con mlx-whisper encadenados automáticamente tras la voz. Probado E2E: 13 frases → 59.4 s de audio → 48 bloques SRT. Siguiente: Fase 3 (escenas, imágenes y clips).

## 1. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Hardware | Todo corre en esta Mac (**M3 Max, 48 GB unificada**, MPS) |
| Backend | **Python** (FastAPI) |
| Interfaz | **Web local**: FastAPI + frontend en localhost (empaquetable en Tauri más adelante si se quiere escritorio) |
| LLM | **llama.cpp** (ya probado y controlado por el usuario) — servido vía `llama-server` (API OpenAI-compatible) |
| TTS | **Qwen3-TTS** (open-source, Apache 2.0; 0.6B/1.7B; soporta español) |
| Voces | **Variables por video** con flujo "Design then Clone": VoiceDesign crea un clip de referencia desde la descripción de la plantilla → `create_voice_clone_prompt` → `generate_voice_clone` sintetiza todas las frases con voz consistente |
| Generación de imagen | **ComfyUI** vía API HTTP/WebSocket, modelo **Z-Image-Turbo**, 9:16 |
| Movimiento de escenas | **Híbrido**: Ken Burns (zoom/pan) por defecto; image-to-video en Comfy opcional por escena |
| Reescalado | **Real-ESRGAN** |
| Interpolación | **RIFE** (24 → 60 fps) |
| Subtítulos | Whisper con timestamps a nivel palabra (**mlx-whisper** o faster-whisper) |
| Música de fondo | **No** (solo voz + subtítulos) |
| Plantillas de estilo | Sí, por nicho. Empezar con 1–2: **curiosidades**, **historia**, (luego **drama/chisme**) |
| Distribución | Solo **exportar el archivo final**; sin subida automática a plataformas |
| Marca de agua | **Opcional** (toggle por proyecto) |
| Idioma de los videos | Español |
| Almacenamiento | **SQLite** (estados, proyectos, escenas, jobs) + archivos en disco por proyecto |

## 2. Plantillas de estilo

Cada plantilla define el "sabor" completo de un nicho y vive en `plantillas/<nombre>/`:

- **Prompts del LLM** por etapa (tono del guion, tipo de gancho, estructura)
- **Estilo visual** para los prompts de imagen (paleta, iluminación, tipo de composición)
- **Descripción de voz** o pool de voces para Qwen3-TTS (ej. curiosidades → voz enérgica; historia → voz grave narrativa)
- **Estilo de subtítulos** (fuente, tamaño, color, animación)
- Parámetros de ritmo (duración objetivo por escena, velocidad de habla)

Iniciales: `curiosidades` y `historia`. Después: `drama-chisme`.

## 3. Pipeline (etapas)

Cada etapa es **idempotente y re-ejecutable individualmente**; su salida se guarda en disco y su estado en SQLite.

| # | Etapa | Entrada | Salida | Herramienta |
|---|---|---|---|---|
| 0 | Ideas | Tema (texto libre) + plantilla | N ideas de video optimizadas para Shorts/TikTok | llama.cpp |
| 1 | Selección | Ideas | Ideas aprobadas y refinadas (**el usuario elige en la UI**) | UI + llama.cpp |
| 2 | Guion | Idea aprobada | Guion 30–60 s: gancho ≤2 s, ritmo alto, cierre/CTA; segmentado en frases | llama.cpp |
| 3 | Metadatos | Guion | Título, descripción, etiquetas (variantes por plataforma YT/TikTok) | llama.cpp |
| 4 | Voz | Guion segmentado + voz de la plantilla | Un audio por frase → concatenación con pausas → `voz.mp3` | Qwen3-TTS |
| 5 | Subtítulos | `voz.mp3` | Timestamps por palabra → `subtitulos.srt` en bloques cortos (2–4 palabras, estilo shorts) | mlx-whisper |
| 6 | Escenas | Subtítulos + guion | Intervalos de ~3–5 s, cada uno con su prompt de imagen (estilo de plantilla + contenido de la frase) | llama.cpp |
| 7 | Imágenes | Prompts de escena | 1 imagen 9:16 por escena (768×1344, ~47 s c/u) | ComfyUI + Z-Image-Turbo |
| 8 | Reescalado | Imágenes | Imágenes ×4 (~7 s c/u) — **se reescala la imagen, no el video**: 12 imágenes vs miles de cuadros | Real-ESRGAN |
| 9 | Clips | Imágenes reescaladas | 1 clip 1080×1920 @24 fps por escena: Ken Burns por defecto, i2v opcional | ffmpeg / ComfyUI |
| 10 | Interpolación | Clips | 24 → 48/60 fps (RIFE v4.6, GPU Vulkan) | RIFE |
| 11 | Armado | Clips + `voz.mp3` + `subtitulos.srt` (+ marca de agua opcional) | **Video final** con subtítulos quemados | ffmpeg |

Flujo de estados por proyecto:
`IDEA → GUION → METADATOS → VOZ → SUBTITULOS → ESCENAS → IMAGENES → UPSCALE → CLIPS → INTERPOLADO → FINAL`

Puntos de revisión humana (la UI pausa y pide aprobación): tras **Selección (1)**, **Guion (2)** y **Imágenes (7)** — son los puntos donde corregir es barato y el error se propaga caro.

## 4. Arquitectura

```
┌─────────────┐   HTTP/WS   ┌──────────────────────────────┐
│  Frontend    │ ◄─────────► │  Backend FastAPI              │
│  (localhost) │             │  · API REST + WebSocket        │
└─────────────┘             │  · Cola de trabajos (asyncio)  │
                            │  · SQLite (estados, proyectos) │
                            └──────┬────────────────────────┘
                                   │ orquesta
     ┌────────────┬──────────┬─────┴──────┬──────────┬─────────┐
     │ llama.cpp   │ ComfyUI  │ Qwen3-TTS  │ Whisper  │ ffmpeg / │
     │ (llama-     │ (API)    │ (local)    │ (mlx)    │ ESRGAN / │
     │  server)    │          │            │          │ RIFE     │
     └────────────┴──────────┴────────────┴──────────┴─────────┘
```

- **Cola de trabajos**: una sola máquina → un worker asíncrono en el propio proceso (sin Redis/Celery). Ejecuta una etapa GPU-pesada a la vez; progreso por WebSocket a la UI.
- **llama.cpp**: el backend consume `llama-server` por su API OpenAI-compatible; el modelo y sus parámetros son configurables. Los prompts del sistema viven en las plantillas (§2), editables sin tocar código.
- **ComfyUI** corre como servicio aparte; los workflows se guardan como **JSON plantilla** con placeholders (prompt, seed, resolución) en `workflows/`.
- **Gestión de memoria**: con 48 GB unificada no todo puede estar cargado a la vez (LLM + Z-Image + TTS + Whisper). El worker carga/descarga servicios por etapa o los mantiene según presupuesto de memoria — a definir en Fase 0 con mediciones reales.

### Estructura de datos (SQLite)

- `temas` — tema de entrada y fecha
- `ideas` — idea, tema_id, estado (propuesta/aprobada/descartada)
- `proyectos` — idea_id, plantilla, estado del pipeline, carpeta
- `guiones`, `metadatos` — 1:1 con proyecto, versionados
- `escenas` — proyecto_id, t_inicio, t_fin, prompt, seed, rutas de imagen/clip
- `jobs` — etapa, estado (pendiente/corriendo/ok/error), log, duración

### Estructura en disco

```
plantillas/<nombre>/     # prompts, estilo visual, voz, subtítulos, ritmo
workflows/               # JSON de ComfyUI con placeholders
proyectos/<slug>/
  guion.json             # frases segmentadas
  metadatos.json
  voces/                 # un audio por frase
  voz.mp3
  subtitulos.srt
  escenas.json
  imagenes/
  clips/
  upscale/
  interpolados/
  final.mp4
```

## 5. Modelos concretos (M3 Max, 48 GB)

| Rol | Modelo | Nota |
|---|---|---|
| LLM (ideas, guiones, metadatos, prompts) | El que el usuario ya usa en llama.cpp | Ya probado; español fuerte requerido |
| TTS | Qwen3-TTS 1.7B VoiceDesign | ✅ Validado en MPS: RTF 1.54, carga 6.7 s; 0.6B como respaldo rápido |
| Imagen | Z-Image-Turbo (6B) en ComfyUI | Turbo = pocos pasos; viable en MPS |
| STT / subtítulos | mlx-whisper large-v3 | Muy rápido en Apple Silicon, timestamps por palabra |
| Upscale | Real-ESRGAN x4 (general) | |
| Interpolación | RIFE (rife-ncnn-vulkan corre en macOS vía MoltenVK) | |
| i2v opcional | WAN 2.2 5B (ti2v) | Experimental en MPS; solo escenas clave |

## 6. Fases de desarrollo

1. ~~**Fase 0 — Validación del entorno**~~ ✅ **Completada** (2026-07-18): todo el stack validado, mediciones y cambios de diseño en [fase0/RESULTADOS.md](fase0/RESULTADOS.md). La memoria se gestiona descargando Z-Image entre etapas con `POST /free` de ComfyUI (~20 GB liberados); TTS (~5 GB) + Whisper (~2 GB) + LLM conviven sin problema.
2. ~~**Fase 1 — Núcleo texto**~~ ✅ **Completada** (2026-07-18): FastAPI + SQLite + worker en hilo, etapas 0–3 con UI de revisión/edición y plantilla `curiosidades`. Nota clave: las peticiones al LLM mandan `chat_template_kwargs: {enable_thinking: false}` — con el modo razonamiento activo, generar 8 ideas tardaba 6+ min; sin él, segundos.
3. ~~**Fase 2 — Audio**~~ ✅ **Completada** (2026-07-20): etapas 4–5. VoiceDesign genera la referencia según la plantilla → el modelo Base la clona y sintetiza todas las frases en lote → concatenación con pausas de 0.3 s + atempo 1.05 → `voz.wav/mp3`. Whisper corre encadenado y produce `palabras.json` (insumo de escenas) + `subtitulos.srt`. La UI tiene reproductor y vista del SRT.
4. **Fase 3 — Visual**: etapas 6–8 (escenas, imágenes vía Comfy, clips Ken Burns).
5. **Fase 4 — Acabado**: etapas 9–11 (ESRGAN, RIFE, armado final con marca de agua opcional).
6. **Fase 5 — Pulido**: cola robusta, reintentos, i2v opcional, plantilla `historia` y luego `drama-chisme`, empaquetado Tauri si se decide.

## 7. Referencias

- Qwen3-TTS: [GitHub](https://github.com/QwenLM/Qwen3-TTS) · [Colección en Hugging Face](https://huggingface.co/collections/Qwen/qwen3-tts) · [Demo](https://huggingface.co/spaces/Qwen/Qwen3-TTS)
