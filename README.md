# Loomcast

Generador automatizado de videos cortos (30–60 s, 9:16) para YouTube Shorts y TikTok, **100% con IA local** en Apple Silicon.

Tema → ideas → guion → metadatos → voz (Qwen3-TTS) → subtítulos (Whisper) → imágenes (Z-Image-Turbo vía ComfyUI) → upscale (Real-ESRGAN) → clips → interpolación (RIFE) → video final.

Ver [PLAN.md](PLAN.md) para la arquitectura completa y [fase0/RESULTADOS.md](fase0/RESULTADOS.md) para las mediciones de rendimiento.

## Requisitos

- macOS con Apple Silicon (desarrollado en M3 Max / 48 GB)
- Python 3.12
- Node 20+ y pnpm (solo para compilar el frontend)
- [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) con un modelo instruct en español
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) con Z-Image-Turbo (bf16), VAE `ae.safetensors` y text encoder `qwen_3_4b`
- ffmpeg

## Arranque

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# Frontend: se compila una vez (y cada vez que lo toques)
cd web && pnpm install && pnpm build && cd ..

# 1. llama-server: solo si tu modelo no declara `comando` en config.toml
#    (con `comando`, lo arranca y lo para Loomcast; ver abajo)
# 2. ComfyUI corriendo (por defecto 8188)

./.venv/bin/uvicorn backend.main:app --port 8700
# UI en http://127.0.0.1:8700
```

## Frontend

Estudio multimedia en **Astro + Svelte + Tailwind** (`web/`), con cuatro modos:
**Vídeos** (el pipeline completo, paso a paso), **Imágenes**, **Música** y
**Biblioteca** (todo lo creado). El color, la tipografía y el espaciado salen de
los tokens de `web/src/styles/global.css`.

`uvicorn` sirve el build estático de `web/dist/`, así que en el día a día basta
con un solo proceso. Para tocar la interfaz con recarga en caliente:

```bash
cd web && pnpm dev
# Astro en http://localhost:4321, con proxy de /api hacia el backend en 8700
```

## Arquitectura del backend

Capas (de HTTP hacia abajo): `routers/` (controllers: validación y JSON, cero lógica) → `services/` (reglas de negocio; `services/pipeline/` son las etapas de generación) → `repositories/` (consultas a SQLite y carga de plantillas) → `models.py` (ORM + máquina de estados). Transversales: `clients/` (adaptadores a llama-server y Qwen3-TTS), `workers/queue.py` (cola de jobs en un hilo, uno a la vez, con encadenado y recuperación), `schemas.py` (contratos Pydantic de la API).

## Flujo de creación (UI)

Tema → ideas → seleccionar/aprobar → y ya en el proyecto, los cinco pasos del
stepper: **1** guion (editar/regenerar) → **2** voz (elegir del banco o crear nueva → generar narración) → **3** metadatos → **4** escenas (generar prompts → editarlos → aceptar y generar imágenes) → **5** armar video final.

Puntos de revisión humana: selección de ideas, guion, elección de voz, y **prompts de escena antes de gastar GPU en las imágenes**.

## Ciclo de vida del LLM

Solo cuatro etapas usan el llama-server (ideas, guion, metadatos y prompts de escena); el resto del pipeline pelea por la misma memoria unificada. Por eso el modelo de texto no vive residente: Loomcast lo **carga al empezar una etapa de texto y lo descarga antes de cualquier etapa de voz/GPU**, igual que ya hacía con ComfyUI (`/free`) y Qwen3-TTS.

Declara cada modelo en `[[llm.modelos]]` de `config.toml` con el script que lo levanta:

```toml
[[llm.modelos]]
id = "qwen3-30b"
nombre = "Qwen3 30B A3B"
comando = "~/scripts/llama-qwen3-30b.sh"
url = "http://127.0.0.1:9876"
```

El script se ejecuta tal cual (con `sh`, desde la raíz del proyecto) y **debe quedarse en primer plano**, sin `&` ni `nohup`, para que Loomcast pueda pararlo; su salida va a `logs/llm-<id>.log`. El sampling, el contexto y el reasoning siguen siendo cosa tuya: Loomcast solo lo arranca y lo para.

- **Selector en la cabecera**: elige cuál de tus modelos se usa. Se guarda en la BD y el relevo (parar uno, arrancar otro) ocurre solo. Con un único modelo declarado el desplegable no aparece.
- **Semáforo LLM**: verde = cargado; **ámbar = descargado a propósito**, se carga solo en la siguiente etapa de texto; rojo = declarado como externo y no responde.
- **Modelo sin `comando`**: externo. Lo levantas tú y Loomcast no lo toca, como siempre. Lo mismo si pones `autostart = false`.
- Si encuentra un llama-server ya escuchando en la url del modelo, lo **adopta** en vez de arrancar otro, y no lo para al terminar: puede ser tuyo.
- Si Loomcast muere de golpe (SIGKILL, cuelgue), al volver a arrancar **recupera la RAM** del llama-server que dejó huérfano (`logs/llm.pid`).
- `inactividad_s` descarga el modelo tras un rato sin usarse, aunque no haya llegado ninguna etapa de GPU.

## Banco de voces

Voces reutilizables generadas con Qwen3-TTS VoiceDesign, guardadas en `voces/<slug>/ref.wav`. Cada proyecto elige una; la narración se produce clonando ese clip. Sembrar 6 de arranque: `./.venv/bin/python scripts/sembrar_voces.py`. Crear más desde la UI describiendo cómo debe sonar.

## Estado

- ✅ Fase 0 — validación del stack completo en local
- ✅ Fase 1 — núcleo de texto: ideas, selección, guion editable, metadatos (UI + jobs)
- ✅ Fase 2 — voz (Qwen3-TTS design-then-clone, narración continua) y subtítulos (mlx-whisper, SRT en bloques de ≤3 palabras)
- ✅ Fase 3 — escenas (prompts visuales en inglés por segmento, **editables antes de generar**), imágenes (Z-Image vía ComfyUI) y **armado estático**: video completo con imágenes fijas, voz, subtítulos compuestos con Pillow y metadatos
- ✅ Banco de voces + flujo de creación por pasos con revisión humana
- ✅ Fase 4 — **video con modos de generación** seleccionables:
  - **Estático** (rápido, ~30s): imágenes fijas + subtítulos quemados + voz. Para iterar.
  - **Ken Burns** (con movimiento): Real-ESRGAN x4 → zoom/paneo nativo a 60fps → subtítulos superpuestos (`overlay` ffmpeg) + voz. Cadena upscale→clips→armado.
  - **Image-to-video** (movimiento IA): anima cada escena con un workflow i2v de ComfyUI + RIFE a 60fps (ver abajo).
- ⬜ Fase 5 (resto) — plantillas `historia`/`drama-chisme`, música, empaquetado

## Modo i2v (image-to-video)

Agnóstico al motor: apuntas `config.toml [i2v].workflow` a un workflow de ComfyUI **en formato API** que tú exportas y ajustas (LTX-Video, WAN, etc.). Requisitos del workflow:

- Incluir los placeholders `{IMAGE}` (nombre del archivo subido), `{PROMPT}` (prompt de la escena) y `{SEED}` en los valores de texto de sus nodos.
- Terminar en un nodo que guarde video (`VHS_VideoCombine` o `SaveVideo`).

Por cada escena, Loomcast sube la imagen, ejecuta el workflow, interpola el clip con **RIFE** (`config.toml [i2v].fps_origen`→`fps_final`) y lo ajusta a la duración del segmento de voz. Luego el armado con movimiento superpone subtítulos y voz. RIFE usa `rife-ncnn-vulkan` (Fase 0) por GPU; ajusta su ruta en `config.toml [rife]`.
