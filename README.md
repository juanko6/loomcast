# Loomcast

Estudio multimedia **100% con IA local** en Apple Silicon. Nada sale de tu
máquina y no hay ninguna API de pago.

Empezó siendo un generador de vídeos cortos y hoy son tres áreas de creación,
más una biblioteca con todo lo hecho:

| | qué hace |
|---|---|
| **Vídeos** | El pipeline completo: tema → ideas → guion → metadatos → voz (Qwen3-TTS) → subtítulos (Whisper) → imágenes → clips → montaje. Formato corto 9:16 (30–60 s) para Shorts y TikTok, con tres modos de montaje (estático, Ken Burns e image-to-video). |
| **Imágenes** | Generar desde texto, editar por instrucciones y quitar el fondo, con varios motores elegibles. |
| **Música** | Pistas instrumentales y canciones con voz cantada y letra, con ACE-Step 1.5 XL Turbo. |
| **Biblioteca** | Todo lo creado en una sola vista. |

Las tres áreas comparten el mismo esqueleto (cola de jobs, cliente de ComfyUI,
LLM local) pero son independientes: puedes usar Música o Imágenes sin tocar el
pipeline de vídeo.

Ver [PLAN.md](PLAN.md) para la arquitectura completa y [fase0/RESULTADOS.md](fase0/RESULTADOS.md) para las mediciones de rendimiento.

## Requisitos

- macOS con Apple Silicon (desarrollado en M3 Max / 48 GB)
- Python 3.12
- Node 20+ y pnpm (solo para compilar el frontend)
- [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) con un modelo instruct en español
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI), con los modelos de lo que vayas a usar:
  - **imágenes**: Z-Image-Turbo (bf16) + VAE `ae.safetensors` + text encoder `qwen_3_4b`; opcionalmente Qwen-Image-Edit 2509 y FLUX.2 Klein (ver "Imágenes")
  - **música**: ACE-Step 1.5 XL Turbo (ver "Música")
- ffmpeg

## Instalación (una vez)

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

El frontend se compila aparte, y hay que recompilarlo cada vez que se toque algo
de `web/` (uvicorn sirve el build estático de `web/dist/`):

```bash
cd web && pnpm install && pnpm build && cd ..
```

Y el parche que la música necesita en Mac (ver "Música"):

```bash
./.venv/bin/python scripts/instalar_parche_mps.py
```

## Arranque diario

Dos procesos, cada uno en su terminal, en este orden.

**1. ComfyUI** (puerto 8188), que es quien genera imágenes, vídeo y música:

```bash
comfy launch -- --enable-manager --enable-manager-legacy-ui --gpu-only
```

**2. Loomcast** (puerto 8700), backend y UI en el mismo proceso:

```bash
./.venv/bin/uvicorn backend.main:app --port 8700
```

La interfaz queda en **http://127.0.0.1:8700**.

El `llama-server` no hay que levantarlo: si el modelo declara `comando` en
`config.toml`, lo arranca y lo para Loomcast según haga falta. Solo si usas un
modelo sin `comando` tienes que levantarlo tú.

Para tocar la interfaz con recarga en caliente, en vez de recompilar a mano, ver
"Frontend".

### Sobre el arranque de ComfyUI

El `--` es obligatorio: separa los argumentos de comfy-cli de los que van a
ComfyUI. Sin él, `comfy launch --gpu-only` intenta interpretar el flag como
suyo.

Si `comfy` no encuentra las dependencias (`ModuleNotFoundError: No module named
'sqlalchemy'` y similares) es que lo estás llamando desde un shell sin el
entorno de ComfyUI. Arranca entonces con su intérprete directamente:

```bash
cd ~/Documents/ComfyUI/ComfyUI && ~/Documents/ComfyUI/venv/bin/python main.py --enable-manager --enable-manager-legacy-ui --gpu-only
```

**`--gpu-only` no es opcional.** En MPS, ComfyUI pone el estado de memoria en
`SHARED`, y con ese estado manda los text encoders a la CPU; en música ese
"text encoder" es el LM de 4B que planifica la canción, así que sin el flag una
pista de 30 s pasa de 30 s a 167 s.

**Y por eso los workflows de imagen llevan `"device": "cpu"` en su `CLIPLoader`.**
Los encoders `qwen_3_4b_fp4_mixed` (Z-Image) y `qwen_3_8b_fp4mixed` (FLUX.2
Klein) llevan tensores fp8 dentro, y Metal no los soporta: con `--gpu-only` y
sin ese `device`, cualquier generación de imagen muere con
`[CLIPTextEncode] Undefined type Float8_e4m3fn`. El input `device` del nodo fija
el dispositivo por encima del flag global, así que la música se queda en GPU y
las imágenes en CPU. Si añades un workflow de imagen nuevo con un encoder fp8 o
fp4mixed, acuérdate de ponerle `"device": "cpu"`.

Dos líneas que conviene mirar en el arranque:

- `[loomcast] Parche de torch.multinomial en MPS activo` — si no está, la música
  fallará en pistas de más de ~33 s (ver "Música").
- `Set vram state to: SHARED` — es lo normal en Mac, no es un problema.

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

Capas (de HTTP hacia abajo): `routers/` (controllers: validación y JSON, cero lógica) → `services/` (reglas de negocio; `services/pipeline/` son las etapas de generación) → `repositories/` (consultas a SQLite y carga de plantillas) → `models.py` (ORM + máquina de estados). Transversales: `clients/` (adaptadores a llama-server y Qwen3-TTS), `workers/queue.py` (cola de jobs en un hilo, uno a la vez, con encadenado y recuperación), `services/progreso.py` (por dónde va el job en curso), `schemas.py` (contratos Pydantic de la API).

### Progreso de la cola

Las etapas que trabajan por lotes (una imagen o un clip por escena) tardan
minutos, así que anotan por dónde van con `progreso.lote(hecho, total, unidad)`.
El indicador de la cabecera lo lee de `/api/jobs` y se rellena a medida que
avanza: *imagen 3 de 11 · ~6 min*. La estimación sale de lo que han tardado los
elementos ya hechos del propio lote, o sea de esta máquina y este modelo, y no
aparece hasta que termina el primero. Las etapas que no van por lotes (voz,
guion, armado) enseñan el tiempo transcurrido, que al menos distingue "va lento"
de "se colgó".

El contador cuenta sobre el trabajo que ese job va a hacer de verdad: los bucles
reanudables saltan lo que ya estaba hecho, y contar sobre el total del proyecto
arrancaría la barra por la mitad.

## Flujo de creación (UI)

Tema → ideas → seleccionar/aprobar → y ya en el proyecto, los cinco pasos del
stepper: **1** guion (editar/regenerar) → **2** voz (elegir del banco o crear nueva → generar narración) → **3** metadatos → **4** escenas (reparto → generar prompts → editarlos → aceptar y generar imágenes) → **5** armar video final.

Puntos de revisión humana: selección de ideas, guion, elección de voz, reparto, y **prompts de escena antes de gastar GPU en las imágenes**.

### Reparto (consistencia de personajes)

Cada escena se prompt-ea por separado, así que el LLM no recuerda lo que
escribió en la anterior: el mismo personaje sale "a young woman" en una escena
y "a woman in her thirties" en otra, y el generador dibuja a dos personas
distintas. Por eso el paso 4 empieza fijando el reparto.

El LLM lee el guion y devuelve, por cada personaje recurrente, una ficha física
en inglés (edad, complexión, pelo, ojos, ropa, un rasgo). Puedes editarla. Al
generar los prompts de escena, el LLM referencia a cada personaje con su
marcador `{CLAVE}` en vez de describirlo, y Loomcast lo sustituye por la ficha
**literal** antes de guardar: lo que se lee en la UI es exactamente lo que se le
manda al generador. Que sea literal es el punto — si se deja que el LLM
parafrasee la descripción en cada escena, el personaje vuelve a derivar, solo
que más despacio.

En el prompt de movimiento se sustituye una forma abreviada ("a woman in her
early thirties"), que ahí solo hace falta saber quién se mueve y el prompt debe
caber en 25-45 palabras.

Un reparto vacío es una respuesta válida: en *curiosidades* es lo normal. En
*drama* casi nunca lo es, y el prompt incluye al narrador aunque el guion nunca
lo describa. Editar una ficha no reescribe los prompts ya generados: hay que
regenerarlos.

Esto fija ropa, pelo, edad y complexión, pero **no la cara**: con solo texto el
generador dibuja una persona nueva cada vez. Para eso está el retrato.

### Retrato de referencia

Cada personaje puede tener su cara oficial, generada desde su ficha con un
encuadre fijo (plano medio, frontal, fondo neutro, luz plana) y guardada en
`proyectos/<slug>/personajes/<CLAVE>.png`. Deliberadamente no lleva el estilo
visual de la plantilla: no es una escena, es una ficha, y en drama la luz dura
del estilo taparía justo lo que hay que ver.

Se hace una vez por personaje y se reutiliza, así que ahí compensa el motor que
mejor cara dé y no el más rápido: `[personajes].motor` en `config.toml` apunta
por defecto a `zimage_retrato`, el mismo Z-Image con 16 pasos en vez de 8
(~80 s en el M3 Max).

### Cómo se usa el retrato

En la etapa de imágenes cada escena va por uno de dos caminos, según lo que
guardó el paso de escenas en su campo `personajes`:

| la escena… | se genera |
|---|---|
| no lleva personajes | texto→imagen con `[imagen].motor_generar`, como siempre |
| lleva personajes con retrato | **a partir de sus retratos**, con `[personajes].motor_escena` |
| lleva personajes sin retrato | texto→imagen; la UI avisa de cuántas son |

El paso 4 dice antes de lanzar cuántas escenas saldrán de las caras del
reparto, y la tira marca cuáles llevan personaje.

Si una escena tiene más personajes que referencias admite el motor, se recorta:
con dos personas y un motor de una sola referencia, entrar con la primera sale
mejor que renunciar a las dos caras — la segunda sigue descrita por su ficha en
el texto.

Dos detalles del camino, por si tocas los workflows de edición:

- Las referencias van como `{IMAGE1}`…`{IMAGE3}`, y **las que no se pasan se
  podan del grafo** (nodo, escalado y la entrada que lo consumía). Así un mismo
  archivo sirve para una referencia o para tres, en vez de mantener tres casi
  iguales.
- El tamaño de salida es `{WIDTH}`/`{HEIGHT}` y ya no se hereda de la
  referencia. Sin eso, meter a un personaje de un retrato 3:4 en una escena la
  devolvía en 3:4 en vez del 9:16 del vídeo.

**En Mac el motor para esto es FLUX.2 Klein, no Qwen-Image-Edit**, aunque Qwen
sea el que está entrenado para llevar personas de una imagen a otra: su nodo
escala las referencias con `interpolate(mode="area")`, que en Metal exige que el
tamaño de entrada sea divisible por el de salida y revienta con *"Adaptive pool
MPS: input sizes must be divisible by output sizes"*. Klein escala con lanczos y
no pasa por ahí. Además tarda lo mismo que Z-Image generando de cero (~84 s
medidos en el M3 Max), así que la consistencia sale casi gratis en tiempo.

## Ciclo de vida del LLM

Solo cinco etapas usan el llama-server (ideas, guion, metadatos, reparto y prompts de escena); el resto del pipeline pelea por la misma memoria unificada. Por eso el modelo de texto no vive residente: Loomcast lo **carga al empezar una etapa de texto y lo descarga antes de cualquier etapa de voz/GPU**, igual que ya hacía con ComfyUI (`/free`) y Qwen3-TTS.

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
- ✅ **Imágenes** — galería propia con generar, editar y quitar fondo, y motores elegibles (Z-Image, Qwen-Image-Edit, FLUX.2 Klein)
- ✅ **Música** — instrumentales y canciones con ACE-Step 1.5 XL Turbo, con conditioning musical, guion de secciones y masterizado EBU R128
- ✅ **Estudio en Astro + Svelte** — los cuatro modos en una sola interfaz, con reproductor global y biblioteca
- ⬜ Pendiente — plantillas `historia`/`drama-chisme`, mezclar la música bajo la narración con ducking, empaquetado

## Imágenes

Tres modos, independientes del pipeline de vídeo:

- **Generar** desde texto. El LLM puede pasar tu idea en español a un prompt en
  inglés; se generan varias previsualizaciones y eliges cuál llega a final.
- **Editar** por instrucciones sobre una imagen que subas ("quítale las gafas").
- **Quitar fondo**, con rembg (u2net vía onnxruntime). No pasa por ComfyUI: es
  una segmentación ligera que corre en CPU y no necesita el pipeline de difusión.

Los motores se declaran en `config.toml [imagen.motores.*]`, cada uno apuntando a
un workflow de ComfyUI en formato API según los modos que sepa hacer:

| motor | genera | edita | notas |
|---|---|---|---|
| **Z-Image Turbo** | ✅ | — | el rápido, y el que usa el pipeline de vídeo para las escenas |
| **Qwen-Image-Edit 2509** | — | ✅ | GGUF + text encoder qwen2.5-vl, para esquivar el fp8 que Metal no soporta. ~2 min por imagen |
| **FLUX.2 Klein 9B** | ✅ | ✅ | GGUF Q8 + encoder fp4mixed. ~50 s generando, ~76 s editando |

`motor_generar` y `motor_editar` fijan cuál se preselecciona; en la galería se
puede cambiar por imagen. Añadir un motor nuevo es declarar su bloque y poner su
workflow, sin tocar código.

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

### Portada

Al terminar de generar una pista se encadena un job que le crea una portada
cuadrada con el motor de imagen por defecto, a partir de un prompt que el LLM
dejó junto al resto de campos. Se ve como miniatura en la lista y a tamaño
completo en el panel de resultado y en el reproductor.

Va después de la pista y no tras la sugerencia del LLM, para que solo tengan
portada las pistas que existen de verdad; cada regeneración estrena la suya. Una
pista rellenada a mano, sin pasar por el LLM, no tiene prompt de portada y se
queda con la miniatura de icono.

384 px por lado (`[musica].portada_px`). Medido con Z-Image en el M3 Max: 256 en
4 s, 320 y 384 en 6 s, 512 en 12 s y 640 en 18 s — 384 sale gratis frente a 320.

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
