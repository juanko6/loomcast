# Loomcast — Plan de proyecto

Estudio multimedia **100% con IA local** en Apple Silicon. Empezó como generador de videos cortos (30–60 s, vertical 9:16) para YouTube Shorts y TikTok, y hoy son tres áreas que comparten esqueleto (cola de jobs, cliente de ComfyUI, LLM local) más una biblioteca: **Vídeos** (el pipeline completo), **Imágenes** (generar, editar, quitar fondo) y **Música** (ACE-Step 1.5).

> Estado (2026-10-19): **fases 0–5 cerradas** — pipeline de vídeo de punta a punta con tres modos de montaje (estático, Ken Burns e i2v), banco de voces, flujo por pasos con revisión humana y LLM agnóstico al modelo. Encima se añadieron dos áreas que no estaban en el plan original (**Imágenes** y **Música**), el front se reescribió en **Astro + Svelte** y el proyecto tiene red de tests (pytest en el backend, Vitest en el front). El i2v pasó a **LTX-2.5** (3× más rápido que HunyuanVideo y a resolución nativa; los dos siguen elegibles al generar). **En curso: Fase 7** — la música del proyecto como pista aparte reutilizable, con mezcla opcional bajo la narración. La cola ya reintenta lo transitorio, la generación se puede parar en caliente desde la interfaz y la plantilla `historia` cierra la Fase 5 con los tres nichos escritos (`curiosidades`, `drama`, `historia`); el reparto completo es la Fase 6.

## 1. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Hardware | Todo corre en esta Mac (**M3 Max, 48 GB unificada**, MPS) |
| Backend | **Python** (FastAPI) |
| Interfaz | **Web local**: FastAPI + frontend en localhost (empaquetable en Tauri más adelante si se quiere escritorio) |
| LLM | **llama.cpp** (ya probado y controlado por el usuario) — servido vía `llama-server` (API OpenAI-compatible) |
| TTS | **Qwen3-TTS** (open-source, Apache 2.0; 0.6B/1.7B; soporta español) |
| Voces | **Variables por video** con flujo "Design then Clone": VoiceDesign crea un clip de referencia desde la descripción de la plantilla → `create_voice_clone_prompt` → `generate_voice_clone` sintetiza todas las frases con voz consistente |
| Generación de imagen | **ComfyUI** vía API HTTP/WebSocket, 9:16. Motores declarados en `config.toml`: **Z-Image-Turbo** (escenas), **Qwen-Image-Edit 2511** (escenas con personaje y edición) y **FLUX.2 Klein 9B** |
| Movimiento de escenas | **Híbrido**: Ken Burns (zoom/pan) por defecto; image-to-video en Comfy opcional por escena |
| Reescalado | **Real-ESRGAN** |
| Interpolación | **RIFE** (24 → 60 fps) |
| Subtítulos | Whisper con timestamps a nivel palabra (**mlx-whisper** o faster-whisper) |
| Música de fondo | **Sí, como pista aparte**: se genera desde la historia del proyecto (ACE-Step 1.5) y se descarga sola, sin narración, para reutilizarla en redes. Mezclarla en el video final por debajo de la voz (ducking) es opcional |
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

Hechas las tres: `curiosidades` (datos sorprendentes), `drama` (storytime de chisme) e `historia` (un hecho real contado como relato, con reparto y estilo de época). El selector de la UI lista el directorio, así que una plantilla nueva aparece sola.

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
| 11 | Armado | Clips + `voz.mp3` + `subtitulos.srt` (+ música y marca de agua opcionales) | **Video final** con subtítulos quemados | ffmpeg |
| M | Música (opcional) | Guion + escenas + duración de la voz | Pista instrumental acorde a la historia, en la biblioteca de Música: **se escucha y se descarga sola**, sin narración | llama.cpp + ACE-Step 1.5 |

La etapa de música va aparte y no entra en la línea de estados: no bloquea el
video y su pista vive en la biblioteca de Música como cualquier otra, para
poder reutilizarla en redes. El armado la mezcla solo si se marca.

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
| i2v opcional | **LTX-2.5** (desde 2026-10-12) y HunyuanVideo 1.5 | Tercer modo de video, y el motor se elige al generar. LTX-2.5 es 3× más rápido y genera a la resolución del video; su GGUF necesita el parche de `scripts/instalar_parches.py`. Los motores se declaran en `[i2v.motores.*]` de config.toml |
| Edición de imagen | Qwen-Image-Edit 2511 (GGUF + Lightning 4 pasos) | Hasta 3 referencias; es el motor de las escenas con personaje |
| Imagen alternativa | FLUX.2 Klein 9B (GGUF Q8 + encoder fp4mixed) | Genera y edita; esquiva el fp8 que Metal no soporta |
| Música | ACE-Step 1.5 XL Turbo | Instrumentales y canciones; **ComfyUI tiene que arrancar con `--gpu-only`** o el LM planificador se va a la CPU (5,5× más lento) |

## 6. Fases de desarrollo

Fuera de esta lista, y ya hecho, está casi todo lo que convirtió el generador de
videos en un estudio: la sección de **Imágenes** (generar, editar, quitar fondo,
con motor elegible), la de **Música** (ACE-Step 1.5, con conditioning musical y
masterizado EBU R128), la **biblioteca** común, el front reescrito en **Astro +
Svelte**, el lanzador `scripts/run-loomcast.sh` y la red de **tests** (pytest en
el backend, Vitest en el front). El [playbook](docs/playbook-nueva-feature.md)
explica cómo se añade una sección nueva siguiendo ese patrón.

1. ~~**Fase 0 — Validación del entorno**~~ ✅ **Completada** (2026-07-18): todo el stack validado, mediciones y cambios de diseño en [fase0/RESULTADOS.md](fase0/RESULTADOS.md). La memoria se gestiona descargando Z-Image entre etapas con `POST /free` de ComfyUI (~20 GB liberados); TTS (~5 GB) + Whisper (~2 GB) + LLM conviven sin problema.
2. ~~**Fase 1 — Núcleo texto**~~ ✅ **Completada** (2026-07-18): FastAPI + SQLite + worker en hilo, etapas 0–3 con UI de revisión/edición y plantilla `curiosidades`. Nota clave: las peticiones al LLM mandan `chat_template_kwargs: {enable_thinking: false}` — con el modo razonamiento activo, generar 8 ideas tardaba 6+ min; sin él, segundos.
3. ~~**Fase 2 — Audio**~~ ✅ **Completada** (2026-07-20): etapas 4–5. VoiceDesign genera la referencia según la plantilla → el modelo Base la clona y sintetiza todas las frases en lote → concatenación con pausas de 0.3 s + atempo 1.05 → `voz.wav/mp3`. Whisper corre encadenado y produce `palabras.json` (insumo de escenas) + `subtitulos.srt`. La UI tiene reproductor y vista del SRT.
4. ~~**Fase 3 — Visual**~~ ✅ **Completada** (2026-07-21): etapas 6–8 (escenas, imágenes vía Comfy, clips Ken Burns).
5. ~~**Fase 4 — Acabado**~~ ✅ **Completada** (2026-07-21): etapas 9–11 (ESRGAN, RIFE, armado final con marca de agua opcional).
6. **Fase 5 — Pulido y movimiento** ✅: ✅ i2v opcional (HunyuanVideo 1.5 en julio, **LTX-2.5** desde octubre y el motor elegible al generar; tercer modo en la UI, regeneración por escena) y RIFE 24→60 fps ✅. La cola reanuda tras un reinicio (`recuperar_pendientes()` re-encola lo que quedó a medias) ✅, **reintenta sola los fallos transitorios** con espera creciente y tope configurable (`[cola]` de `config.toml`), distinguiéndolos de los de validación, que siguen fallando a la primera ✅, y **la generación se puede parar desde la interfaz** —lo que corre, la cola entera o las dos— cortando ComfyUI, el proceso externo, los bucles por lotes, el LLM (respuesta en streaming, se abandona entre trozos) y Whisper (entre segmentos), sin dejar archivos a medias ni encadenar la etapa siguiente ✅; lo único que no se puede partir es la síntesis de Qwen3-TTS, y ahí la UI avisa en vez de aparentar que corta. Y los tres nichos están escritos: `curiosidades`, `drama` e `historia` ✅. **Fase cerrada.**
7. **Fase 6 — Reparto completo**: arranca sobre el trabajo de agosto 2026 (cara de referencia por personaje, escenas generadas desde el retrato, reparto editable a mano, personaje que no muta entre escenas). Faltan: voz por personaje (clone TTS ligada a cada cara, en vez del banco de 6 voces por video), QA de consistencia con embeddings ArcFace entre escenas del mismo personaje (marcar y regenerar automáticamente las que desentonan) y cast persistente reutilizable entre videos.
8. **Fase 7 — Música del proyecto** (en curso): la música nace de la **historia que se está contando**, no de una idea suelta. El LLM lee el guion y las escenas y escribe el brief musical (estilo en prosa, tempo, tonalidad, guion de secciones) con la duración de la narración; ACE-Step sintetiza la pista y queda en la **biblioteca de Música como una pista propia**: se escucha, se descarga sola —sin narración— y se reutiliza en redes, que es el motivo de que vaya aparte y no solo incrustada. Mezclarla en el video final es un interruptor del armado: `sidechaincompress` baja la cama cuando habla la voz y la deja subir en los silencios, con fades de entrada y salida. El proyecto puede también apuntar a una pista que ya exista en la biblioteca en vez de generar una nueva. El plan original excluyó música de fondo; ahora que el área de Música está completa, se integra así.
9. **Fase 8 — Series**: objeto "serie" que agrupa proyectos con continuidad: el LLM recibe el resumen del episodio anterior y el cast recurrente; marcas de episodio en thumbnail/overlay. Lo que mejor funciona en Shorts: episodios con personajes recurrentes.
10. **Fase 9 — Autopiloto y lotes**: tema → video final en un clic, con las aprobaciones humanas configurables por paso; lotes de N ideas → N videos en cola con prioridad. Pasa de herramienta a línea de producción.
11. **Fase 10 — Export y empaquetado**: app de escritorio con Tauri, export multi-formato (9:16, 1:1, 16:9), thumbnail automático desde el mejor frame, variantes A/B de títulos, y upload opcional (yt-dlp) por decidir (el plan original decía sin subida automática).

## 7. Referencias

- Qwen3-TTS: [GitHub](https://github.com/QwenLM/Qwen3-TTS) · [Colección en Hugging Face](https://huggingface.co/collections/Qwen/qwen3-tts) · [Demo](https://huggingface.co/spaces/Qwen/Qwen3-TTS)
