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
# 2. ComfyUI corriendo (por defecto 8188), SIEMPRE con --gpu-only:
#    comfy launch -- --gpu-only        (o: python main.py --gpu-only)
#    Sin ese flag ComfyUI deja los text encoders en la CPU en todos los Mac, y
#    la música tarda 5,5× más. Ver "Música" más abajo.

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

## Música (ACE-Step 1.5 XL Turbo)

Sección independiente del pipeline de vídeo, con dos modos: `instrumental` (fondo
o jingle) y `cancion` (voz cantada + letra). El modelo es **ACE-Step 1.5 XL
Turbo**, con soporte nativo en ComfyUI (sin custom nodes). Descarga a
`ComfyUI/models/` desde `Comfy-Org/ace_step_1.5_ComfyUI_files`:
`acestep_v1.5_xl_turbo_bf16` (diffusion_models), `qwen_0.6b_ace15` y
`qwen_4b_ace15` (text_encoders) y `ace_1.5_vae` (vae). **No uses los GGUF que
circulan**: son para `acestep.cpp`, y ComfyUI-GGUF no soporta esta arquitectura.

Dos cosas hacen la calidad, y las dos van en contra de la intuición de v1:

- **La descripción de estilo es prosa, no etiquetas.** 1.5 quiere un párrafo que
  diga qué instrumentos hay y **qué papel tiene cada uno en la mezcla** ("a soft
  sub-bass anchors the track without intruding"). Una lista coma-separada al
  estilo de v1 rinde peor. Los prompts de `prompts/musica_*.md` ya piden esto.
- **El conditioning musical (BPM, tonalidad, compás) es obligatorio y decide.**
  Es lo que v1 no tenía: sin él el arreglo deriva de tempo y tonalidad dentro de
  la misma pista, y los instrumentos chocan y se tapan. Los rellena el LLM y son
  editables en la UI; `services/musica_combos.py` los normaliza contra las
  listas cerradas del nodo (un valor fuera de lista hace fallar el prompt entero
  en ComfyUI).

### ComfyUI necesita `--gpu-only`

**Sin este flag la música tarda 5,5× más.** ComfyUI decide en
`model_management.py` que en MPS el estado de memoria es `SHARED`, y
`text_encoder_device()` solo manda el text encoder a la GPU si el estado es
`HIGH_VRAM` o `NORMAL_VRAM` — así que en **todos** los Mac los text encoders caen
a la CPU. Para Z-Image o Flux da igual (el encoder corre medio segundo), pero en
ACE-Step 1.5 ese "text encoder" es un LM de 4B que genera el plan de la canción
de forma autorregresiva, cientos de pasos secuenciales. En CPU eso son minutos.

Medido en M3 Max, 30 s de pista, misma seed: **166,6 s en CPU → 30,1 s con
`--gpu-only`** (16,1 s si los modelos ya están en memoria; la diferencia es
cargar el encoder de 8,38 GB, que se paga en cada pista porque el pipeline
libera los modelos al terminar).

El LM planificador se apaga con `config.toml [musica].audio_codes = false`: baja
a ~2 s por pista, pero sin plan de estructura y con peor calidad.

### Masterizado

ACE-Step entrega el audio crudo: cada pista sale a un volumen distinto y con los
picos pegados al techo (medido: ~-12 LUFS con picos de +0,2 a +0,3 dBTP, o sea
distorsionando). Al terminar, Loomcast pasa la pista por **loudnorm de ffmpeg en
dos pasadas** (EBU R128): la primera mide y la segunda corrige con esas medidas.
En una sola pasada loudnorm va a ciegas y aplasta la dinámica.

Resultado sobre una pista real: **-12,6 → -14,0 LUFS** y **pico +0,2 → -1,2
dBTP**, con el LRA intacto en 1,1 LU — nivel corregido sin comprimir. El
original queda al lado como `crudo.flac`, y lo que se sirve y se reproduce es
`musica.flac`. Se ajusta con `[musica].lufs` y `[musica].true_peak`; `lufs = 0`
lo desactiva.

Esto **no** arregla una mezcla embarullada: no separa instrumentos ni reequilibra
nada. Eso viene del modelo y se ataca desde el prompt y el guion de secciones.

### El parche de `torch.multinomial` es obligatorio

```bash
python scripts/instalar_parche_mps.py
```

Sin él, el muestreo del LM planificador devuelve tokens corruptos y la
generación muere con un `index -33790 is out of bounds for dimension with size
64000` que señala a un nodo sin culpa (los errores de MPS son asíncronos). Es un
bug de PyTorch, no de ACE-Step: `torch.multinomial` sobre Metal devuelve a veces
índices cuya probabilidad es **exactamente 0.0**. Lo dispara la presencia de
entradas a cero — aquí, los ~153k tokens del vocabulario que no son códigos de
audio y van enmascarados — y la tasa sube con cuántas haya. Reproducible en
PyTorch puro con `scripts/repro_multinomial_mps.py`; en CPU no pasa nunca.

Se manifiesta de dos formas y las dos importan: por encima de ~33 s el índice se
sale del rango y **tumba** la generación (33 s va, 34 s falla siempre), y por
debajo cae dentro del rango y **degrada el plan en silencio**.

El parche quita los ceros antes de muestrear y traduce el índice de vuelta:
misma distribución, sin lo que dispara el fallo. Va en `custom_nodes/`, que es
lo que `comfy update` no toca, con el código versionado aquí y un symlink allí.
Comprueba que cargó buscando esta línea en el arranque de ComfyUI:

```
[loomcast] Parche de torch.multinomial en MPS activo
```

Si ComfyUI renombrase `sample_manual_loop_no_classes`, el custom node fallaría
al importar y ComfyUI lo registraría como nodo no cargado: sale en el log, pero
es fácil pasarlo por alto. Merece una mirada después de cada `comfy update`.

Alternativa sin parche: `[musica].lm_device = "cpu"`, que no depende de nada
pero es ~7× más lento (90 s de pista en ~410 s frente a 60 s).

## Modo i2v (image-to-video)

Agnóstico al motor: apuntas `config.toml [i2v].workflow` a un workflow de ComfyUI **en formato API** que tú exportas y ajustas (LTX-Video, WAN, etc.). Requisitos del workflow:

- Incluir los placeholders `{IMAGE}` (nombre del archivo subido), `{PROMPT}` (prompt de la escena) y `{SEED}` en los valores de texto de sus nodos.
- Terminar en un nodo que guarde video (`VHS_VideoCombine` o `SaveVideo`).

Por cada escena, Loomcast sube la imagen, ejecuta el workflow, interpola el clip con **RIFE** (`config.toml [i2v].fps_origen`→`fps_final`) y lo ajusta a la duración del segmento de voz. Luego el armado con movimiento superpone subtítulos y voz. RIFE usa `rife-ncnn-vulkan` (Fase 0) por GPU; ajusta su ruta en `config.toml [rife]`.
