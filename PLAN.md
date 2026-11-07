# Loomcast — Plan de proyecto

Estudio multimedia **100% con IA local** en Apple Silicon. Empezó como generador de videos cortos (30–60 s, vertical 9:16) para YouTube Shorts y TikTok, y hoy son tres áreas que comparten esqueleto (cola de jobs, cliente de ComfyUI, LLM local) más una biblioteca: **Vídeos** (el pipeline completo), **Imágenes** (generar, editar, quitar fondo) y **Música** (ACE-Step 1.5).

> Estado (2026-11-07): **fases 0–5, 7–9 y 11 cerradas; en curso la 6 y la 10.** Lo último: la **Fase 10** arrancó con la **publicación y el liberado** (apuntar que el vídeo está subido, metadatos listos para pegar en cada red y dejar solo el `final.mp4`); la **Fase 11**, fuera del plan original, añade el **modo motion**, que dibuja el vídeo por código con la plantilla `explica`; Imágenes tiene un cuarto modo, la **imagen animada** en bucle con LTX-2.5 (vertical u horizontal, hasta 4K), y Música suma **álbumes** (misma banda y semilla, intención distinta por pista) y **lotes** de pistas por API.
>
> Lo anterior: pipeline de vídeo de punta a punta con tres modos de montaje generados (estático, Ken Burns e i2v), banco de voces, flujo por pasos con revisión humana, LLM agnóstico al modelo y la música del proyecto como pista aparte reutilizable con mezcla opcional bajo la narración. Encima se añadieron dos áreas que no estaban en el plan original (**Imágenes** y **Música**), el front se reescribió en **Astro + Svelte** y el proyecto tiene red de tests (pytest en el backend, Vitest en el front). El i2v pasó a **LTX-2.5** (3× más rápido que HunyuanVideo y a resolución nativa; los dos siguen elegibles al generar). La cola ya reintenta lo transitorio, la generación se puede parar en caliente desde la interfaz y la plantilla `historia` cierra la Fase 5 con los tres nichos escritos (`curiosidades`, `drama`, `historia`). Las **series** (Fase 8) ya están: proyectos que son episodios de una misma historia, con reparto fijo que viaja a cada capítulo, el resumen del anterior como contexto del guion siguiente, plantilla propia con guion de líneas atribuidas y marca de episodio quemada en el vídeo. **Fase 9 cerrada**: autopiloto por proyecto y lotes de un tema, con las paradas de revisión configurables, prioridad en la cola y una parada que detiene la tirada entera. **En curso: Fase 6** — el reparto completo: el **cast persistente** y la **voz por personaje** ya están (personajes guardados aparte y reutilizables entre vídeos, cada uno con su voz del banco, y narración sintetizada por tramos), y queda el QA de consistencia con ArcFace.

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

Hechas cinco: `curiosidades` (datos sorprendentes), `drama` (storytime de chisme), `historia` (un hecho real contado como relato, con reparto y estilo de época), `serie` (un episodio de una historia que continúa, la única con guion de líneas atribuidas) y `explica` (un proceso o un sistema dibujado por escenas, la única con `montaje: "motion"`). El selector de la UI lista el directorio, así que una plantilla nueva aparece sola.

## 3. Pipeline (etapas)

Cada etapa es **idempotente y re-ejecutable individualmente**; su salida se guarda en disco y su estado en SQLite.

| # | Etapa | Entrada | Salida | Herramienta |
|---|---|---|---|---|
| 0 | Ideas | Tema (texto libre) + plantilla | N ideas de video optimizadas para Shorts/TikTok | llama.cpp |
| 1 | Selección | Ideas | Ideas aprobadas y refinadas (**el usuario elige en la UI**) | UI + llama.cpp |
| 2 | Guion | Idea aprobada | Guion 30–60 s: gancho ≤2 s, ritmo alto, cierre/CTA; segmentado en frases | llama.cpp |
| 3 | Metadatos | Guion | Título, descripción, etiquetas (variantes por plataforma YT/TikTok) | llama.cpp |
| 4 | Voz | Guion + voz del proyecto (y la de cada personaje, si la tiene) | Un audio por tramo (narrador / líneas de un personaje) → concatenación con pausas → `voz.mp3` | Qwen3-TTS |
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

En el **modo motion** (Fase 11) la etapa 6 escribe **fichas de composición** en
vez de prompts de imagen, y las etapas 7–10 se cambian por el dibujo de cada
escena con Pillow, que entrega los fotogramas crudos a ffmpeg. Voz, subtítulos,
música y armado son los mismos.

Flujo de estados por proyecto:
`IDEA → GUION → METADATOS → VOZ → SUBTITULOS → ESCENAS → IMAGENES → UPSCALE → CLIPS → INTERPOLADO → FINAL`

Puntos de revisión humana (la UI pausa y pide aprobación): tras **Selección (1)**, **Guion (2)** y **Imágenes (7)** — son los puntos donde corregir es barato y el error se propaga caro.

Subir el vídeo no es una etapa: pasa fuera de Loomcast. Que esté subido se
**apunta** en el proyecto (fecha, enlace y nota), porque es lo único suyo que no
se deduce mirando su carpeta, y a partir de ahí se puede **liberar** el material
intermedio y dejar solo el `final.mp4` (Fase 10).

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
- `proyectos` — idea_id, plantilla, estado del pipeline, carpeta y, si es un episodio, su serie, su número y el resumen de en qué quedó
- `series` — nombre, plantilla y el tema del que cuelgan sus ideas de episodio
- `serie_miembros` — reparto fijo de la serie (slugs del reparto propio)
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
| Imagen animada | LTX-2.5 (workflow `loop_ltx25_api.json`) + RIFE + Real-ESRGAN | La misma imagen como guía en el primer cuadro y en el último; 8 fps de condicionamiento para que 15 s quepan sin swap; escalado a Full HD, 2K o 4K |
| Música | ACE-Step 1.5 XL Turbo | Instrumentales y canciones; **ComfyUI tiene que arrancar con `--gpu-only`** o el LM planificador se va a la CPU (5,5× más lento) |

## 6. Fases de desarrollo

Fuera de esta lista, y ya hecho, está casi todo lo que convirtió el generador de
videos en un estudio: la sección de **Imágenes** (generar, editar, quitar fondo,
con motor elegible, y la **imagen animada** en bucle con LTX-2.5), la de
**Música** (ACE-Step 1.5, con conditioning musical, masterizado EBU R128,
**álbumes** de la misma banda y **lotes** de pistas por API), la **biblioteca** común, el front reescrito en **Astro +
Svelte**, el lanzador `scripts/run-loomcast.sh` y la red de **tests** (pytest en
el backend, Vitest en el front). El [playbook](docs/playbook-nueva-feature.md)
explica cómo se añade una sección nueva siguiendo ese patrón.

1. ~~**Fase 0 — Validación del entorno**~~ ✅ **Completada** (2026-07-18): todo el stack validado, mediciones y cambios de diseño en [fase0/RESULTADOS.md](fase0/RESULTADOS.md). La memoria se gestiona descargando Z-Image entre etapas con `POST /free` de ComfyUI (~20 GB liberados); TTS (~5 GB) + Whisper (~2 GB) + LLM conviven sin problema.
2. ~~**Fase 1 — Núcleo texto**~~ ✅ **Completada** (2026-07-18): FastAPI + SQLite + worker en hilo, etapas 0–3 con UI de revisión/edición y plantilla `curiosidades`. Nota clave: las peticiones al LLM mandan `chat_template_kwargs: {enable_thinking: false}` — con el modo razonamiento activo, generar 8 ideas tardaba 6+ min; sin él, segundos.
3. ~~**Fase 2 — Audio**~~ ✅ **Completada** (2026-07-20): etapas 4–5. VoiceDesign genera la referencia según la plantilla → el modelo Base la clona y sintetiza todas las frases en lote → concatenación con pausas de 0.3 s + atempo 1.05 → `voz.wav/mp3`. Whisper corre encadenado y produce `palabras.json` (insumo de escenas) + `subtitulos.srt`. La UI tiene reproductor y vista del SRT.
4. ~~**Fase 3 — Visual**~~ ✅ **Completada** (2026-07-21): etapas 6–8 (escenas, imágenes vía Comfy, clips Ken Burns).
5. ~~**Fase 4 — Acabado**~~ ✅ **Completada** (2026-07-21): etapas 9–11 (ESRGAN, RIFE, armado final con marca de agua opcional).
6. **Fase 5 — Pulido y movimiento** ✅: ✅ i2v opcional (HunyuanVideo 1.5 en julio, **LTX-2.5** desde octubre y el motor elegible al generar; tercer modo en la UI, regeneración por escena) y RIFE 24→60 fps ✅. La cola reanuda tras un reinicio (`recuperar_pendientes()` re-encola lo que quedó a medias) ✅, **reintenta sola los fallos transitorios** con espera creciente y tope configurable (`[cola]` de `config.toml`), distinguiéndolos de los de validación, que siguen fallando a la primera ✅, y **la generación se puede parar desde la interfaz** —lo que corre, la cola entera o las dos— cortando ComfyUI, el proceso externo, los bucles por lotes, el LLM (respuesta en streaming, se abandona entre trozos) y Whisper (entre segmentos), sin dejar archivos a medias ni encadenar la etapa siguiente ✅; lo único que no se puede partir es la síntesis de Qwen3-TTS, y ahí la UI avisa en vez de aparentar que corta. Y los tres nichos están escritos: `curiosidades`, `drama` e `historia` ✅. **Fase cerrada.**
7. **Fase 6 — Reparto completo** (en curso): arranca sobre el trabajo de agosto 2026 (cara de referencia por personaje, escenas generadas desde el retrato, reparto editable a mano, personaje que no muta entre escenas).
   - ✅ **Cast persistente reutilizable entre vídeos**: un reparto propio en `reparto/<slug>/`, con su ficha, su tipo (persona u objeto), su seed y su retrato. Se promueve desde un proyecto (que es cuando se sabe que alguien merece conservarse) y se trae a cualquier vídeo nuevo. Al traerlo **el retrato se copia**, no se referencia, porque los proyectos son autocontenidos en disco y borrar del reparto no puede romper un vídeo ya hecho; **editar la ficha dentro de un proyecto no toca al original**, para lo cual hay una acción explícita de actualizar. Regenerar el casting **conserva** a los traídos y descarta al del LLM que choque con su clave, y traer a alguien cuya clave ya existe le da la siguiente libre (`ANA_2`) en vez de pisar un marcador ya escrito en los prompts.
   - ✅ **Voz por personaje**: la narración se sintetiza **por tramos** y cada personaje del reparto dice sus líneas con su propia voz, en vez de que todo lo narre una sola. La voz de un personaje es una voz **del banco** (no un segundo almacén en paralelo: el banco ya se escucha, se reutiliza y se borra desde un sitio) y se le puede escribir con VoiceDesign desde su **propia ficha**, que es de donde ya sale su retrato. **Viaja con el reparto propio** igual que la ficha y la cara, aunque sin copiarse —es una fila compartida del banco—, así que si se borró de allí el personaje entra sin voz en vez de apuntar a un clip que no está. El formato de guion con líneas atribuidas (`formato_guion: "lineas"`) es **opt-in por plantilla**: cuando se construyó no lo activaba ninguna, y hoy solo lo hace la plantilla `serie` (Fase 8); `curiosidades`, `drama` e `historia` siguen dando un solo tramo con el texto completo, o sea la misma llamada única de antes, y hay un test por plantilla que lo fija. Se construye aquí porque quien lo necesita son las **series** (Fase 8), donde un personaje recurrente tiene que sonar igual en diez episodios. De regalo, la parada en caliente ya corta **entre tramos**: antes la narración no se podía cortar a mitad y ahora cuesta como mucho el tramo que esté sonando, y un tramo que falla no tira la narración entera.
   - ⬜ **QA de consistencia con ArcFace**: embeddings entre escenas del mismo personaje, para marcar y regenerar automáticamente las que desentonan.
8. ~~**Fase 7 — Música del proyecto**~~ ✅ **Completada**: la música nace de la **historia que se está contando**, no de una idea suelta. El LLM lee el guion y las escenas y escribe el brief musical (estilo en prosa, tempo, tonalidad, guion de secciones) con la duración de la narración; ACE-Step sintetiza la pista y queda en la **biblioteca de Música como una pista propia**: se escucha, se descarga sola —sin narración— y se reutiliza en redes, que es el motivo de que vaya aparte y no solo incrustada. Mezclarla en el video final es un interruptor del armado: `sidechaincompress` baja la cama cuando habla la voz y la deja subir en los silencios, con fades de entrada y salida. El proyecto puede también apuntar a una pista que ya exista en la biblioteca en vez de generar una nueva. El plan original excluyó música de fondo; ahora que el área de Música está completa, se integra así.
9. ~~**Fase 8 — Series**~~ ✅ **Completada**: una serie es un **nombre**, una **plantilla** y un **reparto fijo**, y nada más —no tiene estado de producción propio: el ciclo `IDEA → … → FINAL` sigue siendo de cada episodio, y un proyecto sin serie funciona exactamente igual que antes. La continuidad viene de dos sitios: el **reparto fijo**, que se apoya en el reparto propio y entra en cada episodio nuevo con la ficha, la cara y la voz ya puestas (resolviendo la clave ocupada con `ANA_2`, como ya hacía traer a alguien a mano), y el **resumen del episodio anterior**, que escribe el LLM al armar el vídeo —la cola lo encadena sola— y que entra como contexto en el guion del siguiente; es editable, porque es lo que ese guion dará por cierto. «Nuevo episodio» es un clic desde la serie, con un apunte opcional de una línea: numera, trae el reparto y encola el guion. El otro camino es el de siempre —la serie es dueña de un tema y aprobar una de sus ideas crea el episodio siguiente—, así que un proyecto sigue naciendo por un único sitio. La plantilla **`serie`** es la primera que activa `formato_guion: "lineas"` (narración más frases de los personajes, cada uno con su voz del banco) y trae sus ocho prompts escritos para episodios; las otras tres no se enteran. El vídeo sale con la marca «NOMBRE · EP n» quemada arriba a la izquierda, con la fuente y los colores de los subtítulos de la plantilla, en los dos modos de montaje. Disolver una serie no borra sus episodios (se quedan como vídeos sueltos) y borrar uno del medio no rompe los demás.
10. ~~**Fase 9 — Autopiloto y lotes**~~ ✅ **Completada**: Loomcast deja de conducirse paso a paso. El **autopiloto** de un proyecto encadena lo que hoy se pulsa a mano, desde donde esté el proyecto hasta su `final.mp4`, con el modo de montaje y la voz elegidos al lanzarlo (son las mismas dos decisiones que ya se piden a mano). No sigue una escalera fija: **pregunta qué le falta al proyecto**, que es lo que mira el stepper, así que retoma uno a medias sin rehacer nada y relanzarlo tras un fallo es volver a lanzarlo. Las **paradas de revisión son configurables y por defecto se respetan las tres que ya existen** —selección de idea, guion y prompts de escena antes de gastar GPU en las imágenes—: llega hasta la siguiente, deja el proyecto esperando y lo dice; quien quiera producción sin manos las desactiva al lanzar o en `[autopiloto]` de `config.toml`. Un **lote** produce varias ideas de un tema, una detrás de otra (la cola es de un solo hilo a propósito, así que no se paraleliza), y parar en una revisión **libera la línea** para el siguiente, que es lo que hace útil el lote con las paradas puestas. La cola pasa a ordenar por **prioridad y luego llegada**, de modo que rehacer una imagen a mano adelanta a los diez vídeos del lote sin romper los reintentos (que siguen siendo dentro del turno), la parada, el progreso ni el orden interno del lote. Lo delicado quedó así: el autopiloto es **estado y no un job largo**, y el único que encola es el worker tras una etapa que terminó bien y sin parada pedida, de modo que **parar para de verdad** —«parar todo» apaga todas las tiradas antes de cancelar nada—; un fallo no transitorio detiene su proyecto con el motivo escrito y no arrastra al resto del lote; y el encadenado automático pasa por la puerta de memoria de `llm_runtime` como cualquier clic, con un test que lo fija. De paso, una etapa nueva (`generar_retratos`) retrata al reparto entero de una tirada, soltando la memoria una vez y no por cara.
11. **Fase 10 — Export y empaquetado** (en curso):
    - ✅ **Publicación y liberado**: el stepper tiene por fin su último paso. Que un vídeo esté subido es **el único dato del proyecto que no se deduce mirando su carpeta**, así que se apunta a mano —fecha, enlace y nota—, y la lista de vídeos y la biblioteca llevan la marca de «subido», que es la pregunta que uno se hace delante de veinte proyectos. En ese paso están también los textos de los metadatos **en la forma en la que se pegan en cada red** (las etiquetas separadas por comas para la caja de YouTube, y como hashtags para meterlas en el título o en la descripción), porque escribirlos y pegarlos son dos momentos del mismo texto. Y con el vídeo arriba, el material intermedio deja de ser material: **liberar** deja en la carpeta solo el `final.mp4` —el guion, los metadatos, el reparto y el enlace viven en la base, no en disco—, con una lista de lo que se queda y no de lo que se va, de modo que un archivo nuevo del pipeline se tira solo sin tener que acordarse de apuntarlo. No se libera un proyecto sin publicar (ahí todo eso sigue vivo) ni con trabajo en curso, y un proyecto liberado se enseña **hecho** en vez de pedir la voz y las imágenes que se tiraron a propósito: que está liberado se mira en el disco y no en una marca guardada, así que volver a generar las imágenes lo deshace sin que nadie se acuerde de nada.
    - ⬜ **Export multiformato** (9:16, 1:1, 16:9) y **thumbnail automático** desde el mejor frame.
    - ⬜ **Variantes A/B de títulos**.
    - ⬜ **App de escritorio con Tauri**.
    - ⬜ **Subida automática con yt-dlp**: sigue por decidir, como en el plan original. Hoy se sube a mano y el proyecto solo apunta que está subido.
12. ~~**Fase 11 — Motion graphics**~~ ✅ **Completada** (fuera del plan original): un vídeo que no se genera con ComfyUI sino que **se dibuja por código** —un esquema que cada escena declara y que se dibuja sobre negro, con anotaciones que señalan lo que la voz está contando—. No es una categoría aparte sino un **modo de montaje más**, porque comparte el ciclo entero (idea, guion, voz, subtítulos, música, armado, publicación) y produce el mismo mp4 vertical: lo decide la plantilla con `"montaje": "motion"`, y de ahí salen solas la rama de la etapa de escenas, el salto de las imágenes y el reescalado, y el modo en la UI. La escena deja de ser un prompt y pasa a ser una **ficha de composición** (bloque, banda, cámara, texto), que el LLM escribe en dos pasos y que **nada da por buena**: se repara el storyboard antes de pedir ningún texto —porque el bloque decide qué clase de texto se escribe— y luego la ficha; una cifra cuyo número no esté en el guion no se publica, se degrada a titular. Se dibuja con **Pillow**, que ya estaba instalado, en vez de con un navegador: ni Node ni GPU, más rápido, y de paso desaparece el problema de determinismo. Primera plantilla: `explica`. El recorrido entero está en `docs/estilo-motion.md`.

## 7. Referencias

- Qwen3-TTS: [GitHub](https://github.com/QwenLM/Qwen3-TTS) · [Colección en Hugging Face](https://huggingface.co/collections/Qwen/qwen3-tts) · [Demo](https://huggingface.co/spaces/Qwen/Qwen3-TTS)
