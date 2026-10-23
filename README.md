# Loomcast

Estudio multimedia **100% con IA local** en Apple Silicon. Nada sale de tu
máquina y no hay ninguna API de pago.

Empezó siendo un generador de vídeos cortos y hoy son tres áreas de creación,
más una biblioteca con todo lo hecho:

| | qué hace |
|---|---|
| **Vídeos** | El pipeline completo: tema → ideas → guion → metadatos → voz (Qwen3-TTS) → subtítulos (Whisper) → imágenes → clips → montaje, más la música de la historia. Formato corto 9:16 (30–60 s) para Shorts y TikTok, con tres modos de montaje (estático, Ken Burns e image-to-video). |
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
- Un servidor de LLM con API de OpenAI y un modelo instruct en español: [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`) o [MLX](https://github.com/ml-explore/mlx-lm) (`mlx_lm.server`)
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI), con los modelos de lo que vayas a usar:
  - **imágenes**: Z-Image-Turbo (bf16) + VAE `ae.safetensors` + text encoder `qwen_3_4b`; opcionalmente Qwen-Image-Edit 2511 y FLUX.2 Klein (ver "Imágenes")
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

Y los parches que ComfyUI necesita aquí: los dos de Metal (la música y la
edición con referencias) y el del GGUF de LTX-2.5. Cada uno está explicado
en su sección, y el script los enlaza todos:

```bash
./.venv/bin/python scripts/instalar_parches.py
```

## Arranque diario

Todo de una vez, con los logs de cada servicio entremezclados y prefijados, y
Ctrl+C para pararlo todo de forma ordenada:

```bash
scripts/run-loomcast.sh
```

Admite `--lan` (accesible desde la red local), `--dev` (añade Astro en 4321 con
recarga en caliente; entonces la UI buena es esa) y `--sin-comfy` (si ya llevas
ComfyUI por tu cuenta). Si ComfyUI ya escucha en su puerto, lo reutiliza en vez
de levantar otro, y avisa si no ve cargados los parches de `custom_nodes/`. Da
por hecho que ComfyUI está en `~/Documents/ComfyUI`; con otra ruta,
`COMFY_DIR=/donde/sea scripts/run-loomcast.sh`. Con `--ayuda` lo resume todo.

A mano son dos procesos, cada uno en su terminal, en este orden.

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

### El backend se reinicia solo; ComfyUI se queda en pie

Si el backend muere, el lanzador **lo relanza** (hasta tres veces, con 5 s entre
intentos) y deja ComfyUI en marcha. El motivo es el coste: levantar ComfyUI y
recargar un modelo de 20 GiB desde disco son minutos, y la caída que se ve de
verdad —el OOM del kernel, `Killed: 9` sin traza— se arregla en segundos. Al
volver, `recuperar_pendientes()` re-encola los jobs que quedaron a medias.

El aviso queda en `logs/loomcast.log`, pegado a la traza si la hubo (un SIGKILL
del kernel no deja ninguna, y entonces estas dos líneas son todo lo que queda):

```
[lanzador] el backend se reinicia: murió tras 10s en pie
[lanzador] reinicio 1 de 3; ComfyUI y el LLM siguen en pie
```

El tope de tres es lo que evita el bucle infinito cuando no es una caída sino
que **no arranca**: un error de import muere igual de rápido las tres veces, así
que a la cuarta el lanzador se rinde y cierra todo. Si aguanta 5 minutos en pie,
la cuenta vuelve a cero. Ctrl+C sigue parando todo de forma ordenada, y si quien
muere es ComfyUI (o el Astro de `--dev`) se cierra todo como antes: ahí no hay
nada que relanzar en su sitio sin volver a pagar su arranque.

El llama-server no lo lleva el lanzador, sino el backend. El que quedó huérfano
se descarga al volver (`logs/llm.pid`), y eso es lo correcto justo aquí: si el
backend murió por falta de memoria, esos GiB son el problema.

**Y al cerrar con Ctrl+C también se va el LLM.** El backend lo apaga en su
lifespan, pero si no le llega el TERM —o murió antes— el LLM se queda: lo
arrancó con grupo propio para poder matarle los hijos, así que ese grupo no cae
con el lanzador. Quedaba huérfano (`ppid` 1) con sus 22 GiB dentro y nada lo
decía. Ahora la limpieza remata lo que el backend registró en `logs/llm.pid`, y
**solo eso**: un `llama-server` o un `mlx_lm` que hayas levantado tú no está en
ese fichero y no se toca, que para eso existen los modelos sin `comando`.

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

### `POST /free` sí suelta con `--gpu-only`, pero no cuando devuelve

Loomcast le pide a ComfyUI que descargue sus modelos (`POST /free` con
`unload_models` y `free_memory`) antes de cada etapa que vaya a pedir memoria.
**Ese POST no descarga nada**: solo enciende una bandera en la cola de ComfyUI,
que su hilo de ejecución atiende *entre prompts*. Devuelve 200 en **1 ms** con
los modelos todavía dentro.

Medido en el M3 Max con `--gpu-only` y Z-Image cargado:

| momento | memoria libre |
|---|---|
| con Z-Image + su encoder dentro | 16,4 GiB |
| 0,6 s después del POST | **10,0 GiB** |
| 1,7 s después del POST | 27,0 GiB |

Dos cosas, y las dos importan:

1. **Suelta de verdad** — los ~10,6 GiB vuelven, con `--gpu-only` incluido. El
   flag fuerza los encoders a la GPU (`text_encoder_device()` mira
   `args.gpu_only` directamente), pero el estado de memoria sigue siendo
   `SHARED` en MPS y la descarga funciona igual.
2. **Tarda ~1,7 s, y en el camino la memoria libre BAJA** a 10,0 GiB. Descargar
   mueve los pesos al dispositivo de offload, que en un Mac es la misma memoria
   unificada: durante un instante existen las dos copias. O sea que el momento
   justo después del POST es **el peor posible** para lanzar otro modelo.

No busques la descarga en `logs/comfy.log`: ComfyUI la registra en `debug`, así
que no deja ni una línea. Lo único que aparece es un `Using RAM pressure cache.`
suelto. Para verlo, `curl -s localhost:8188/system_stats` y mira el `vram_free`
del dispositivo — en MPS no es "VRAM" sino la memoria disponible del sistema,
que es justo la cifra que mira el kernel al decidir a quién mata.

Esto es lo que mató al backend con `Killed: 9` el 2026-10-19: se pidió el
`/free` y se lanzó un MLX de ~20 GiB acto seguido, con los 11,7 GiB de Z-Image
sin soltar. Ahora `asegurar()` espera a ver la memoria antes de lanzar (ver
"Ciclo de vida del LLM").

**Si ComfyUI no suelta**, la causa habitual es que tenga un workflow en marcha
—lanzado desde su propia UI, por ejemplo—, porque la bandera solo se atiende
entre prompts. Loomcast repite el POST a los 4 s y espera hasta
`[comfy].espera_liberacion_s` (20 s); pasado eso, el job falla diciendo cuánta
memoria había antes y después, en vez de lanzar el modelo y dejar que el kernel
elija a quién mata.

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

Capas (de HTTP hacia abajo): `routers/` (controllers: validación y JSON, cero lógica) → `services/` (reglas de negocio; `services/pipeline/` son las etapas de generación) → `repositories/` (consultas a SQLite y carga de plantillas) → `models.py` (ORM + máquina de estados). Transversales: `clients/` (adaptadores a llama-server y Qwen3-TTS), `workers/queue.py` (cola de jobs en un hilo, uno a la vez, con prioridad, encadenado, recuperación y reintentos), `services/autopiloto.py` (la tirada automática de un proyecto y los lotes), `services/progreso.py` (por dónde va el job en curso), `parada.py` + `services/cancelacion.py` (la bandera de parada y el corte en caliente del job que corre), `schemas.py` (contratos Pydantic de la API).

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

### Reintentos

Un job que se cae por algo de fuera —ComfyUI que todavía no responde, un proceso
externo que se pasa de su tope, el llama-server reiniciándose— se reintenta solo,
con espera creciente, hasta `[cola].intentos` de `config.toml` (3 por defecto,
esperando 20 s y luego 40 s). El job conserva su fila y su cuenta de intentos, y
la etapa encadenada sale una sola vez, tras el intento bueno.

Lo que **no** se reintenta es lo que no se arregla repitiendo: los `ValueError`
de las validaciones de cada etapa («Faltan clips de las escenas…», «No hay
escenas», «La mezcla de música está activada pero el proyecto no tiene pista…»),
un archivo o un binario que no está, un ffmpeg que sale con error, y cualquier
bug nuestro. Tampoco se reintenta un job cuyo proyecto o pista se borró mientras
fallaba. El criterio, excepción por excepción, está comentado en
`backend/workers/queue.py` (`TRANSITORIOS`).

### Parar la generación

Endpoints: `POST /api/jobs/{id}/cancelar` (uno), `POST /api/jobs/parar` (con
`{"corriendo": bool, "pendientes": bool}`) y `GET /api/jobs/historial`.

El botón rojo de la cabecera (y el de cada sección: Vídeos, Música e Imágenes)
para lo que se está generando y vacía la cola; el chip de la cola abre un panel
con la etapa en curso, lo que espera, los dos modos de parada —solo lo actual, o
todo— y los últimos trabajos con su resultado. Pide confirmación, como los
borrados: **se conserva todo lo ya terminado** (las imágenes, los clips y las
pistas completas) y **se descarta lo que estuviera a medio hacer**.

Un job que todavía espera turno se cancela sin más: se marca `cancelado` y el
worker lo salta cuando le llega. El que está corriendo hay que cortarlo de
verdad, y cada familia de etapa espera en un sitio distinto, así que se corta por
todas (`backend/services/cancelacion.py` orquesta; la bandera vive en
`backend/parada.py`, abajo, porque la miran también los `clients/*`):

1. **ComfyUI** (imágenes, upscale, clips i2v, música): `POST /interrupt` más un
   `POST /queue {clear}`. El trabajo corre dentro de ComfyUI y aquí solo se
   sondea su `/history`; sin el interrupt habría que esperar los 1800 s del tope.
2. **Procesos externos** (ffmpeg, ESRGAN, RIFE): todos pasan por
   `backend/procesos.py`, que guarda el que está en marcha. Se le manda SIGTERM
   —así ffmpeg cierra el archivo que estaba escribiendo— y SIGKILL al que no
   muera en 5 s, para que parar no deje la cola esperando a un proceso sordo.
3. **Los bucles por lotes** (una imagen o un clip por escena): miran la bandera
   entre elemento y elemento y salen limpios. Lo ya generado se queda hecho;
   cortar solo el elemento en curso haría que la etapa empezara el siguiente.
4. **El LLM** (ideas, guion, metadatos, reparto, prompts de escena, brief
   musical): `clients/llm.py` pide la respuesta **en streaming** y mira la
   bandera entre trozos. No es por enseñar el texto mientras sale —ninguna etapa
   lo aprovecha—: con la respuesta de un tirón el hilo se queda bloqueado dentro
   de httpx hasta que el modelo termina el guion entero, y pulsar Parar no lo
   tocaría. Al salir se cierra la conexión y el servidor abandona la generación.
   Lo que no se puede partir es la lectura del prompt, antes del primer trozo.
5. **Whisper** (subtítulos, y el `ref_text` del clonado): `clients/stt.py`
   recorre los segmentos a mano en vez de con `list()`, porque el generador de
   faster-whisper decodifica uno por vuelta: entre uno y otro se puede abandonar
   sin haber escrito nada.

**Una síntesis de voz no se puede cortar por dentro**: cada llamada a Qwen3-TTS
es una sola llamada a PyTorch sin puntos de control. Lo que sí se puede es
cortar **entre tramos**: la narración se sintetiza tramo a tramo (el narrador y
las líneas de cada personaje, ver «Voz por personaje»), así que una parada
cuesta como mucho el tramo que estuviera sonando. Con los guiones de un solo
tramo —los de las tres plantillas de hoy— ese «como mucho» sigue siendo la
narración entera.

Si la parada llega durante la carga del modelo, no se paga ninguna síntesis: se
atiende antes del primer tramo. Si llega con un tramo en marcha, ese tramo
termina; con varios, lo que quedaba no se sintetiza y no se escribe un audio a
medias. La UI no promete lo que no puede hacer: el job expone `sin_corte` (de
`cancelacion.SIN_CORTE`), que nombra **el trozo** que no se puede partir —el
tramo, no la etapa—, y el botón lo avisa en la confirmación. `crear_voz` y la
transcripción de `clonar_voz` siguen siendo de una pieza.

Un job parado **no encadena** la etapa siguiente, ni siquiera si el handler llegó
a terminar justo antes del corte: encadenar sería lo contrario de lo que se
pidió. Y el archivo a medio escribir se borra (`_ffmpeg.sin_restos`): un clip o
un `final.mp4` truncado existe en disco, y el resto del pipeline lo daría por
hecho —`ffmpeg concat` se salta sin fallar el clip que no puede abrir y
entregaría un vídeo al que le falta una escena—. En el historial, `cancelado` es
un estado propio y se lee «Parado», distinto de «Error»: pararlo fue una
decisión, no un fallo.


## Autopiloto y lotes

Loomcast se conduce paso a paso: cada etapa es un botón del stepper y entre
botón y botón hay una persona mirando. Eso es lo que quieres mientras afinas una
plantilla, y lo que no quieres cuando ya sabes lo que sale: diez vídeos son
ciento diez clics. El **autopiloto** encadena las etapas de un proyecto hasta su
`final.mp4`, y un **lote** produce varias ideas de un tema, una detrás de otra.

```
POST   /api/proyectos/{id}/autopiloto            lanzar (modo, motor, voz, paradas)
POST   /api/proyectos/{id}/autopiloto/continuar  seguir tras una revisión
DELETE /api/proyectos/{id}/autopiloto            apagarlo y cortar lo que tenga en cola
POST   /api/lotes          {tema_id, modo, motor, voz, paradas}
GET    /api/lotes          en qué proyecto va cada lote, en qué etapa y cuántos quedan
```

El modo de montaje y la voz se eligen **al lanzarlo**, igual que se eligen a mano
en el paso de vídeo y en el de voz: son las mismas dos decisiones y ninguna tiene
un valor obvio. Sin voz elegida no arranca, y lo dice ahí mismo en vez de fallar
dos minutos después al generar la narración.

### Las paradas de revisión, y por qué por defecto se respetan

Son las tres que ya tiene el flujo a mano, las tres donde corregir es barato y el
error se propaga caro:

| parada | qué revisa | qué cuesta saltársela |
|---|---|---|
| `idea` | qué ideas se producen | producir ocho vídeos de ocho ideas mediocres |
| `guion` | el texto que lo decide todo | media hora de GPU sobre un guion malo |
| `escenas` | los prompts antes de las imágenes | la etapa cara, hecha sobre planos que no querías |

El autopiloto llega hasta la siguiente parada, **deja el proyecto esperando y lo
dice** («Esperando que revises el guion»); seguir es un botón, *Visto, continuar*.
Que paren por defecto es deliberado: es lo que hace hoy el flujo a mano. Quien
quiera producción sin manos las desactiva al lanzar, o cambia
`[autopiloto].paradas` en `config.toml` para que el valor por defecto sea otro.

En un lote, la parada de `idea` es la que decide **qué entra**: con ella puesta
solo se producen las ideas aprobadas a mano; sin ella entran también las
propuestas, y entonces es «tema → vídeos» sin tocar nada. Las descartadas no
entran nunca: descartarlas ya fue una decisión. En el autopiloto de un proyecto
suelto esa parada ya está pasada, porque el proyecto existe justo porque alguien
aprobó su idea.

### Qué etapa toca ahora

No hay una escalera fija de pasos: el autopiloto **pregunta qué le falta al
proyecto**, que es lo mismo que mira el stepper. Por eso una tirada lanzada sobre
un proyecto a medias arranca donde esté y no rehace lo que ya hay, y por eso
retomarla tras un fallo es volver a lanzarla. El orden que sale es el de siempre:

```
guion → reparto → metadatos → voz → subtítulos → retratos → escenas → imágenes
      → música (brief → pista) → [montaje]
```

El **reparto va antes de la voz** y no después: con el formato de líneas el
guion ya dice quién habla, y cada uno dice las suyas con su propia voz, que se
escribe desde su ficha. Fijarlo después dejaba el episodio entero narrado por
una sola voz, porque al narrar todavía no había nadie en el reparto.

La voz encadena los subtítulos, la música encadena su pista y el montaje encadena
lo suyo (upscale → clips → armado, o i2v → armado) por la cadena de la cola de
siempre, no por una vía aparte. La **música** son dos jobs y no uno porque son
dos modelos que no caben juntos: el brief lo escribe el LLM desde esta historia
y la pista la sintetiza ComfyUI, y entre job y job la cola descarga el
llama-server. Va justo antes del montaje, cuando ya están el guion, los planos y
la duración de la narración, de los que sale. Como a mano no hay quien pulse el
interruptor de la mezcla, el autopiloto lo enciende él: una banda sonora escrita
para esta historia que no suena en su vídeo sería media etapa. Una pista elegida
a mano de la biblioteca no se toca, y `[autopiloto].musica = false` en
`config.toml` deja el vídeo solo con narración. Los **retratos** también entran,
con una etapa propia (`generar_retratos`) que retrata de una tirada a todo el reparto que no tenga
cara: a mano se piden uno a uno porque uno mira la cara que salió y decide si la
rehace, y en automático eso serían N clics. Suelta la memoria una vez al final y
no tras cada personaje, que sería descargar y recargar ~19 GB por cara.

Si lo que falta sigue siendo lo que acaba de terminar, la tirada se detiene y lo
dice en vez de repetir la etapa para siempre; y hay un tope de etapas por tirada
para el caso de un ciclo de dos (un montaje que dice que terminó sin dejar el
`final.mp4` vuelve al primer job del modo, y ese otra vez al montaje).

### El lote es secuencial

Un lote es un `Autopiloto` por proyecto y un orden. **Solo uno produce a la vez**,
porque la cola de jobs es de un solo hilo a propósito: las etapas se pelean por la
misma memoria unificada, y meter dos modelos grandes a la vez es justo lo que mata
al backend. Cuando el que corría deja la línea —acabó, falló o se paró en una
revisión— entra el siguiente. Que una parada de revisión **libere la línea** es lo
que hace útil el lote con las paradas puestas: si no, un lote de diez se quedaría
clavado en el primer guion y los otros nueve no empezarían nunca; así la máquina
sigue trabajando mientras revisas.

**Un vídeo que sale mal no tira los otros nueve.** Un fallo que no se arregla
repitiendo (los reintentos de lo transitorio siguen siendo los de la cola, y el
autopiloto no se entera de ellos hasta que el job acaba) detiene **su** tirada,
deja el motivo escrito —«Falló «generar_voz»: Falta el clip de referencia de la
voz 'narrador'»— y la línea sigue con el proyecto siguiente.

### Lo que se pide a mano adelanta

La cola pasa a ordenar por **prioridad y luego llegada**: 0 lo que pide una
persona, 10 lo que encola un autopiloto. Con diez vídeos en producción, rehacer
una imagen del proyecto que estás mirando tardaba lo que quedara del lote —media
tarde—, y eso convertía la cola en una lista de espera. Dentro de cada prioridad
sigue siendo una FIFO, así que un lote conserva su orden interno, y una cadena
hereda la prioridad de quien la abrió (un upscale pedido a mano no pierde el sitio
al llegar a los clips). La prioridad vive también en la columna del job para que
`recuperar_pendientes()` restituya el orden tras un reinicio.

Los reintentos no cambian: un job reintenta **dentro de su turno**, sin
re-encolarse, así que no pierde su sitio ni su cuenta de intentos.

### Parar para de verdad

Esto es lo delicado y es donde está puesto el cuidado. Un autopiloto que volviera
a encolar la etapa siguiente por su cuenta sería algo que no se puede detener: la
parada corta el job que corre y vacía la cola, y él la volvería a llenar. Por eso:

- **El autopiloto es estado, no un job largo.** Vive en la tabla `autopilotos` y
  quien lo mueve es el worker: al terminar bien una etapa le pregunta qué falta.
  El único que encola es el worker, y solo tras una etapa que terminó bien **y**
  sin que se pidiera parar. Ninguna etapa encola nada desde dentro.
- **«Parar todo» apaga todos los autopilotos**, y lo hace *antes* de cancelar los
  jobs: así, cuando el worker termine de cortar la etapa en curso y venga a
  preguntar qué toca, ya no hay a quién seguir. Los que esperaban revisión también
  se apagan —el botón dice parar—, y relanzarlos es un clic que retoma cada
  proyecto donde esté. La confirmación dice cuántas tiradas se apagan.
- **«Detener lo actual» no apaga la línea**: corta una etapa, no el lote. El
  autopiloto de ese proyecto se detiene igual (su etapa sube como cancelada y el
  worker se lo dice) y el lote sigue con el siguiente.
- Un job cancelado **antes** de correr no pasa por el handler, pero su autopiloto
  se entera igual; si no, se quedaría «corriendo» sin nada en la cola, o sea
  colgado para siempre.

### La memoria

El autopiloto encadena LLM → TTS → ComfyUI una y otra vez, que es exactamente la
secuencia que mató al backend con `Killed: 9` el 2026-10-19. No hay atajo: las
etapas que encola pasan por la cola de siempre, o sea por la descarga del
llama-server antes de cualquier etapa que no sea de texto y por la espera **real**
de memoria de `llm_runtime` (que no lanza el modelo hasta comprobar que ComfyUI
soltó; ver «Antes de lanzar un modelo se comprueba que cabe»). Hay un test que lo
fija: una tirada entera tiene que pasar por esa puerta en cada etapa, y el día que
alguien encole desde dentro de un pipeline, falla.

En un lote largo tampoco se van acumulando modelos: cada etapa de GPU suelta lo
suyo al terminar, y el vigilante de inactividad descarga el llama-server cuando
lleva un rato sin usarse, incluso con la tirada parada en una revisión.

**Soltar un modelo tampoco es inmediato.** Matarlo devuelve el control enseguida
—el proceso muere, su puerto queda libre— pero el kernel tarda en reclamar sus
22 GiB, y la etapa siguiente empezaba a cargar encima: el 2026-10-20, generando
la voz de un episodio de serie, el MLX se paró como debía (*«parando
mlx-qwen36-35b: empieza generar_voz»*) y el pico del TTS detrás se fue casi
20 GiB al swap. Es el mismo error que el del `/free`, en el otro sentido: allí no
esperábamos a que ComfyUI soltara, aquí no esperábamos a que el sistema
recogiera. Ahora `liberar()` no vuelve hasta ver de vuelta tres cuartos de lo que
ocupaba el modelo (`[llm].espera_devolucion_s`, 20 s de tope), y lo deja medido
en el log y en el historial del job: *«Memoria devuelta: 9.0 → 26.0 GiB (+17.0 de
los 22 que ocupaba, en 2.3 s)»*. No falla nunca: si no vuelve, se anota y se
sigue, porque bloquear la etapa siguiente no la haría caber.

Tres cuartos y no todo porque exigir el 100 % sería agotar el tope siempre: entre
el compresor, la fragmentación y lo que el propio backend tenga dentro, lo último
no vuelve. Lo que importa es que lo que falte ya no sea un modelo entero.

### De dónde sale la cifra de memoria

De `psutil.virtual_memory().available`, en `backend/memoria.py`. Antes salía de
`/system_stats` de ComfyUI, que para MPS devuelve lo mismo —ComfyUI lo mide así
por debajo—, pero ataba la medición a que ComfyUI estuviera escuchando, y hace
falta justo cuando puede no estarlo: al soltar un modelo con ComfyUI cerrado, o
con `--sin-comfy`.

Y es `available`, no «libre»: en macOS la memoria *libre* de `vm_stat` no dice si
cabe un modelo. El 2026-10-20, con el episodio a medias, `vm_stat` daba 1,0 GiB
libres y 25,5 GiB ocupados por el compresor (con 48,1 GiB de contenido dentro),
mientras `available` daba 39,2 GiB — y los 39 son los reales, porque la memoria
inactiva y la comprimida se reclaman en cuanto alguien pide.

Con ComfyUI cerrado, el `POST /free` no lo recoge nadie: no hay descarga en
camino, así que no se esperan los 20 s de rigor y el error no le echa la culpa a
ComfyUI, que es mandar a buscar donde no es. Dice que la memoria la tiene otra
cosa y a dónde mirar: un `llama-server` o un `mlx_lm` suelto, o el compresor.

### Qué cuenta la interfaz

El chip de la cola pasa a decir por qué vídeo va el lote (*imagen 3 de 11 · ~6 min
· vídeo 2 de 8*), y su panel lleva un bloque con el tema, cuántos van hechos, en
qué proyecto y en qué etapa está, cuántos quedan por empezar, cuántos esperan
revisión y cuántos fallaron. El listado de proyectos marca con un chip los que
están en automático (`auto`) y los que esperan que alguien los lea (`revisar`).
Dentro del proyecto, encima del stepper, hay una tira que dice qué está haciendo
la tirada, por qué se detuvo si se detuvo, y los botones de *Visto, continuar* y
*Detener autopiloto*. El stepper sigue estando y sigue funcionando a mano: lo que
se pulse ahí adelanta en la cola a lo que esté encolando el autopiloto.


## Plantillas de estilo

Una plantilla define el sabor completo de un nicho y vive en
`plantillas/<nombre>/`: un `plantilla.json` (voz, estilo visual, subtítulos y
ritmo) y una carpeta `prompts/` con los ocho prompts de sistema del pipeline de
texto y de escenas. El selector de la UI se alimenta de `/api/plantillas`, que
lista el directorio: una carpeta nueva aparece sola, sin tocar código.

| plantilla | qué cuenta | voz | ritmo |
|---|---|---|---|
| **curiosidades** | datos sorprendentes y hechos poco conocidos, con giro final | grave de documental, ágil | 45 s, escenas de 4 s, atempo 1.05 |
| **drama** | storytime de chisme: un conflicto cotidiano que escala | joven y cómplice | 50 s, escenas de 4 s, atempo 1.0 |
| **historia** | un hecho real contado como relato: situación, tensión y desenlace con consecuencia | grave y pausada | 55 s, escenas de 5 s, atempo 1.0 |
| **serie** | un episodio de una historia que continúa: mismo reparto, algo que pasa hoy y un hilo abierto para el siguiente | cercana y narrativa | 50 s, escenas de 4 s, atempo 1.0 |

`serie` es la única con `formato_guion: "lineas"` (ver «Series»): su guion es
narración más frases de los personajes, cada uno con su voz.

`historia` es la que más se apoya en el resto del pipeline, y por eso vale como
ejemplo de hasta dónde llega una plantilla:

- **Guion en `formato_guion: "narracion"`**, como *drama* y al revés que
  *curiosidades*. El formato de frases da frases independientes y sonoras, que
  es justo lo que quiere un dato suelto; un relato necesita lo contrario —
  encadenar por causa y consecuencia, y que la voz saque las pausas de la
  puntuación de un párrafo seguido. En frases sueltas, el mismo hecho suena a
  entrada de enciclopedia leída en voz alta.
- **El reparto no es opcional**: el relato sigue a alguien de principio a fin,
  así que `casting.md` obliga a fijar al protagonista aunque el guion solo lo
  nombre por su oficio (el escribano, la viuda, el grumete), y `escena.md` lo
  pide en la mayoría de los planos por su marcador. Un reparto vacío aquí casi
  siempre es un error, al contrario que en *curiosidades*.
- **Época sin anacronismos**: ropa, materiales, herramientas, arquitectura y
  luz (vela, candil, ventana, día encapotado) pertenecen al periodo, y el
  storyboard fija uno solo para todo el vídeo.
- **Nadie reconocible**: la gente de la época sí, un personaje histórico
  identificable no. El generador lo hace mal y el relato se sostiene mejor
  sobre quien estaba alrededor del hecho. Tampoco escudos, banderas ni uniformes
  de un estado o un ejército reales.

El ajuste fino de una plantilla solo se ve generando un vídeo entero: lo que se
puede comprobar sin GPU es que carga, que aparece en el selector y que las
etapas de texto la usan.

## Flujo de creación (UI)

Tema → ideas → seleccionar/aprobar → y ya en el proyecto, los pasos del
stepper: **1** guion (editar/regenerar) → **2** voz (elegir del banco o crear nueva → generar narración) → **3** metadatos → **4** escenas (reparto → generar prompts → editarlos → aceptar y generar imágenes) → **música** (opcional, se entra a mano) → **5** armar video final.

Puntos de revisión humana: selección de ideas, guion, elección de voz, reparto, y **prompts de escena antes de gastar GPU en las imágenes**.

Ese mismo recorrido se puede dejar en automático —de donde esté el proyecto hasta
el `final.mp4`, parando en las revisiones— y producir varias ideas de un tema
seguidas (ver «Autopiloto y lotes»).

Si la historia continúa, el proyecto puede ser el **episodio de una serie**: el
reparto y el resumen del capítulo anterior entran solos, y el resto del flujo es
idéntico (ver «Series»).

El paso **2 voz** lleva además las voces del reparto: qué voz dice las líneas de
cada personaje y el botón para crearle una desde su ficha (ver «Voz por
personaje»). El reparto se fija en el paso 4, así que si el guion trae líneas
atribuidas y todavía no hay nadie, el paso lo dice en vez de callarse.

### Música de la historia

El paso de **Música** compone la banda sonora de *ese* vídeo: el LLM lee el
guion y los planos de las escenas y escribe el brief para ACE-Step (estilo en
prosa, tempo, tonalidad y guion de secciones), con la duración que dura la
narración. Dos detalles del prompt son los que hacen que sirva: la música sale
del tema y la emoción de la historia, y se escribe como cama para una voz
(nada cantado, medios despejados, sin melodía que compita).

La pista **no se queda dentro del vídeo**: nace como una pista más de la
biblioteca de Música, así que se escucha, se descarga suelta —sin narración— y
se reutiliza en redes. En el mismo paso se puede enganchar una pista que ya
tengas en la biblioteca en lugar de generar otra.

Mezclarla en el vídeo final es un interruptor aparte. Al activarlo, el armado
(los dos modos) la mete por debajo de la voz con `sidechaincompress`: la cama
baja sola cuando se habla y sube en los silencios, con fades de entrada y
salida. El nivel y los fades se ajustan en `[video]` de `config.toml`
(`musica_db`, `musica_fade_s`); el ducking en sí vive en
`backend/services/pipeline/_mezcla.py`. Hay que rehacer el vídeo para oírla, y
si la mezcla está activada sin pista lista el armado falla en vez de entregar
un vídeo en silencio.

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
lo describa; en *historia* tampoco, porque el relato sigue a un protagonista
aunque solo se le nombre por su oficio. Editar una ficha no reescribe los prompts ya generados: hay que
regenerarlos.

El reparto también se edita a mano: se pueden **añadir y quitar** personajes. Hace
falta porque el casting se deja gente — alguien que sale en varias escenas sin
nombre ni diálogo ("el escritor del sótano") puede no entrar, y entonces cada
escena se lo inventa distinto. Tras añadirlo hay que regenerar los prompts, o
pegar su ficha en las escenas donde salga: **quién sale se relee del prompt cada
vez que se guarda**, no solo al generarlo.

Dos tolerancias del sustituidor, por si ves algo raro:

- Si el modelo escribe la clave sin llaves (`MADRASTRA stands alone…`, que pasa)
  se reconoce igual. Las claves van en mayúsculas y en español, así que no se
  confunden con el prompt, que es inglés en minúscula.
- Un marcador que no corresponda a nadie pierde las llaves y se queda como
  texto, en vez de llegar al generador como `{ALGUIEN}`.

Y un aviso sobre las fichas: se pegan literales en un prompt en inglés, así que
**escríbelas en inglés y en positivo**. Añadir "no rasgos asiáticos" no funciona
por partida doble — está en otro idioma y es una negación, y estos modelos
generan con CFG 1, sin condicionamiento negativo real, así que el concepto entra
igual. Si quieres unos rasgos concretos, dilos afirmando: *"pale Northern
European features"*.

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

**Persona u objeto.** El reparto admite objetos a propósito: un barco, un mapa o
una máquina que vuelve en varias escenas tampoco debe mutar. Pero el encuadre no
puede ser el mismo, y aquí hubo un bug que se vio con la plantilla `historia`: el
encuadre de persona pide cara, cabeza visible y textura de piel, así que a un
mapa descrito con «no humans are visible» le pintaba un rostro encima — cinco
términos pidiendo cara le ganan a una negación. Ahora cada miembro del reparto
tiene su tipo, y lo decide el casting sin preguntar: **leyendo la ficha**, no
haciendo caso al LLM. Se le pide el campo, pero mlx_lm ignora el `json_schema` y
aun cuando llega se equivoca —en este proyecto había un cofre, un Motorola
DynaTAC, un robot y un mapa, los cuatro marcados «persona»—. La ficha sí es
fiable, porque el prompt dicta qué lleva: para una persona, edad aparente,
complexión, tono de piel, color de pelo y de ojos y una cláusula final
`wearing ...`; para un objeto, forma, material y desgaste. Con dos de esas
señales o más es una persona, con ninguna un objeto, y con una sola desempata lo
que dijo el LLM. Las palabras van completas, que «chair» lleva «hair» dentro.
Los repartos hechos antes de esto se recolocan solos al arrancar. Un objeto se retrata con su propio encuadre (sujeto centrado, fondo
liso, sin nombrar nada humano y negándolo al final) y el prefijo que se le pasa
al motor de escena habla de «subjects», no de «people». El tipo no se edita a
mano: la tarjeta del reparto solo lo enseña, para que se entienda por qué ese
miembro se retrata sin cara, y reescribir su ficha lo revisa.

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

**El motor para esto es Qwen-Image-Edit 2511**, que es el que está entrenado
para llevar a una persona de una imagen a otra. Medido en el M3 Max con los
mismos retratos, prompt y semilla:

| motor | 1 referencia | 2 referencias | qué sale |
|---|---|---|---|
| **Qwen-Image-Edit 2511** | 132 s | 200 s | los rasgos y la ropa del retrato se reconocen |
| Qwen-Image-Edit 2509 | 137 s | 205 s | compone bien pero deriva: otra camiseta, otro pantalón, caras genéricas |
| FLUX.2 Klein 9B | 102 s | — | el más rápido y con buena atmósfera, pero deja la cara en sombra, y solo admite una referencia |

Qwen necesita el parche de MPS (`python scripts/instalar_parches.py`): sus
nodos escalan las referencias con `interpolate(mode="area")`, que en Metal exige
que el tamaño de entrada sea divisible por el de salida y si no revienta con
*"Adaptive pool MPS: input sizes must be divisible by output sizes"*. Sin el
parche no hay edición con referencias en Mac, con 2511 ni con 2509.

### Reparto propio (reutilizable entre vídeos)

Todo lo de arriba fija a un personaje **dentro** de un vídeo. Pero el personaje
cuelga de su proyecto y muere con él, así que un narrador que vuelve en diez
vídeos había que describirlo y retratarlo diez veces, y salía distinto. El
**reparto propio** es el almacén que sobrevive al vídeo: vive en
`reparto/<slug>/retrato.png` (mismo patrón que `voces/<slug>/ref.wav`) y se
maneja desde el desplegable «Reparto propio» del paso 4.

Tres acciones, y el orden importa:

- **Guardar en el reparto** promueve a alguien de un proyecto. El alta es así, y
  no un formulario en blanco, porque el momento en que uno sabe que quiere
  conservar a un personaje es cuando ya tiene la ficha afinada y una cara que
  convence, y eso pasa dentro de un vídeo. Se le pone un nombre («Ana, la
  narradora»), que es lo que lo distingue en el listado; viaja su ficha, su
  `tipo` (persona u objeto, que decide el encuadre del retrato) y su seed, para
  que rehacerle la cara «con el mismo seed» en otro vídeo dé la misma persona, y
  **su voz del banco**, para que un narrador recurrente que ya sonaba bien no
  vuelva a sonar distinto (ver «Voz por personaje»).
- **Traer** lo mete en el proyecto abierto con la ficha y la cara ya puestas.
- **Actualizar en el reparto** sube al almacén la versión que hay en un
  proyecto. Hace falta porque **editar la ficha dentro de un proyecto no toca al
  original**: un retoque para una escena concreta no puede cambiar al personaje
  en todos los vídeos futuros.

**El retrato se copia, no se referencia.** Los proyectos son autocontenidos en
disco y eso ha salido bien: borrar del reparto no puede romper un vídeo ya hecho
ni cambiar uno antiguo por detrás. Al traer a alguien, su `retrato.png` se copia
a `proyectos/<slug>/personajes/<CLAVE>.png` y desde ahí el proyecto es dueño de
su copia. Borrar del reparto solo borra su carpeta y hace que los personajes que
venían de él olviden de dónde vinieron (mismo criterio que al borrar una voz del
banco); su ficha y su cara siguen en el proyecto.

Dos choques que había que resolver, y cómo quedaron:

- **Regenerar el reparto reemplaza el reparto completo del proyecto**, y eso se
  llevaría también a los traídos del almacén. Ahora **sobreviven**: perderlos
  sería lo peor de las dos opciones, porque el usuario los eligió a mano, su
  retrato ya está copiado y su marcador puede estar escrito en los prompts de
  escena, que quedarían nombrando a nadie. Conservarlos no es a ciegas: si el
  LLM acaba de escribir a alguien con la misma clave, **manda el del reparto** y
  el del LLM se descarta, porque tener una ficha canónica que no deriva entre
  vídeos es justo para lo que se guardó. El log de la etapa lo dice marcando a
  cada uno con «(del reparto)», y la UI avisa antes de pulsar.
- **Las claves son marcadores `{CLAVE}` ya escritos en los prompts.** Traer a
  alguien cuya clave ya existe en el proyecto no puede pisar al que estaba ni
  dejar dos con el mismo marcador, porque la sustitución es por texto y el
  segundo se quedaría con la ficha del primero. Entra con la siguiente libre
  (`ANA_2`, `ANA_3`…) y la UI avisa de con qué clave entró, que es la que hay
  que escribir en los prompts.

A diferencia del banco de voces, aquí no se encola nada: promover y traer son
copiar un PNG y escribir una fila, sin GPU ni LLM, así que van en el hilo HTTP
y la UI ve el resultado al instante.

## Series (episodios con continuidad)

Lo que mejor funciona en Shorts no es un vídeo bueno: son diez con la misma
gente y una historia que avanza. Una **serie** es eso, y en Loomcast son tres
cosas y ninguna más: un **nombre**, una **plantilla** y un **reparto fijo**. No
tiene estado de producción propio —el ciclo `IDEA → … → FINAL` es de cada
episodio— y **un proyecto sin serie sigue funcionando exactamente igual que
antes**: sin serie no hay contexto extra en el guion, ni marca en el vídeo, ni
nada que cerrar.

Se crea desde el desplegable «Nueva serie» de la columna de Vídeos, y a partir
de ahí la serie tiene su propia vista: su reparto fijo, sus episodios y el botón
que se usa a diario.

### La continuidad viene de dos sitios

- **El reparto fijo**, que se apoya en el reparto propio. La serie guarda a
  quién hay que traer, y cada episodio nuevo se los trae con su ficha, su cara y
  su voz ya fijadas: nadie vuelve a describir al protagonista en el capítulo
  cuatro, y el generador no le cambia la cara. Como las claves son marcadores
  `{CLAVE}` que acaban escritos en los prompts, traer a dos con la misma clave
  da `ANA` y `ANA_2` en vez de pisar al primero (lo resuelve el mismo
  `clave_libre` del reparto propio). Añadir o quitar a alguien afecta a los
  episodios **siguientes**: un capítulo ya escrito no gana ni pierde personajes
  por detrás.
- **El resumen del episodio anterior**. Al armar el vídeo de un episodio, la
  cola encadena un job más que escribe en qué quedó: qué pasó, cómo acabó y qué
  queda abierto. Ese texto entra como contexto en el guion del episodio
  siguiente. Es **editable** —en el paso «Vídeo final», junto al vídeo— porque
  es lo que el capítulo siguiente dará por cierto: un detalle inventado que
  nadie corrige se vuelve canon de la serie. El job se puede relanzar a mano
  tras cambiar el guion.

### Cómo se produce una serie

1. **Crear la serie** con su nombre y la plantilla `serie`.
2. **Fijar el reparto**: promover a los personajes buenos al reparto propio
   (desde el paso de escenas de cualquier vídeo) y añadirlos a la serie. Se hace
   una vez.
3. **Nuevo episodio**, con un apunte opcional de una línea («Ana encuentra la
   llave»). En blanco, el episodio lo propone el LLM desde donde quedó el
   anterior. Un clic: crea el episodio, lo numera, le trae el reparto y encola
   su guion.
4. **El episodio es un proyecto normal**: guion, voz, metadatos, escenas,
   imágenes, música y montaje, con los mismos pasos y las mismas revisiones.
5. **Al armar el vídeo** se escribe su resumen, y el episodio siguiente ya nace
   sabiendo en qué quedó.

El otro camino es el flujo de siempre: la serie es dueña de un **tema**, y las
ideas de ese tema son ideas de episodio (con el `ideas.md` de la plantilla de
serie, que piensa en capítulos y no en vídeos sueltos). Aprobar una de ellas
crea el episodio siguiente por el mismo sitio, `ideas.crear_proyecto`, así que
no hay dos maneras distintas de nacer un proyecto. Ese tema no se lista aparte
en la columna de Temas: tiene el mismo nombre que la serie y se entra a él desde
el botón «Pedir ideas de episodio».

### La plantilla `serie`

Es la primera que activa `formato_guion: "lineas"`, el formato de guion con
líneas atribuidas que se construyó en la Fase 6 y que hasta ahora no usaba
ninguna. Su guion es narración más frases de los personajes —el narrador lleva
la historia y alguien dice de 3 a 6 líneas puntuales, cada una con **su voz del
banco**—, y el resto de sus ocho prompts está escrito para episodios: ideas que
son capítulos de una secuencia, títulos que funcionan para quien entra por el
cuarto, storyboard con una localización que se repite y casting que solo fija a
los que la serie añade. Las otras tres plantillas no se enteran de nada: siguen
con su formato de siempre, y hay un test que lo fija.

### La marca de episodio

El vídeo de un episodio sale con «NOMBRE DE LA SERIE · EP 3» quemado arriba a la
izquierda, por debajo de la zona que las apps tapan con su interfaz. Va quemada
porque el título de la publicación se corta y no viaja cuando alguien reenvía el
archivo. Usa la fuente y los colores de los subtítulos de la plantilla (es el
vídeo el que tiene un look, no la marca) y se dibuja con Pillow, como los
subtítulos: en el montaje con movimiento es un PNG transparente superpuesto con
`overlay` durante todo el vídeo, y en el estático se estampa en cada still. Un
proyecto sin serie no añade ni la entrada ni el overlay.

### Borrar sin romper nada

- **Disolver la serie** no borra sus episodios: cada uno lleva su guion, su
  narración, su reparto copiado y su vídeo, y perderlos por disolver la serie
  sería una pérdida desproporcionada (el mismo criterio que al borrar un tema
  con proyectos). Se quedan como vídeos sueltos, que es lo que son sin serie, y
  el tema de las ideas sigue siendo un tema normal. Lo que se va es la serie y
  su reparto fijo.
- **Borrar un episodio** del medio no rompe los demás: los números no se
  recalculan (el 4 ya se publicó llamándose 4) y el siguiente episodio continúa
  el anterior que quede, saltándose el hueco.
- **Borrar a alguien del reparto propio** lo saca también del reparto fijo de
  las series. Aquí no basta con desvincular como en los personajes de un
  proyecto: esas filas son la orden de traerlo a cada episodio nuevo, y dejarlas
  haría fallar la creación del siguiente.

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

No tiene que ser llama.cpp: vale cualquier servidor con API de OpenAI. Con
**MLX** (`mlx_lm.server`), el `comando` lleva el modelo y el puerto:

```toml
[[llm.modelos]]
id = "mlx-qwen38-27b"
nombre = "Qwen3.8 27B (MLX)"
comando = "~/Models/mlx/venv/bin/mlx_lm.server --model mlx-community/Qwen3.8-27B-4bit --port 9876"
url = "http://127.0.0.1:9876"
model = "mlx-community/Qwen3.8-27B-4bit"
```

**El `model` es obligatorio ahí.** `mlx_lm.server` trata ese campo como un repo
de Hugging Face y se lo descarga si no lo tiene, así que con el `"local"` que
Loomcast manda por defecto responde un 404 (*Repository Not Found for url:
.../models/local*). llama.cpp, en cambio, ignora el campo y usa el modelo que ya
tiene cargado.

Los repos `-MTP-` de mlx-community **no se sirven sueltos**: son el *drafter* de
decodificación especulativa, el equivalente al `--model-draft` de llama.cpp, y
van en `--draft-model`. A día de hoy mlx-lm no los carga de ninguna de las dos
formas (*Model type qwen3_5_mtp not supported*); el soporte está en el PR #990,
todavía abierto, así que de MLX solo se declaran las variantes normales y el
35B A3B con MTP va por llama.cpp.

Un script que empiece pidiendo `sudo` (por ejemplo `sudo sysctl
iogpu.wired_limit_mb=...`) no sirve para arranque automático: Loomcast no puede
responder a la petición de contraseña. Declara ese modelo sin `comando` y
levántalo tú.

- **Selector en la cabecera**: elige cuál de tus modelos se usa. Se guarda en la BD y el relevo (parar uno, arrancar otro) ocurre solo. Con un único modelo declarado el desplegable no aparece.
- **Semáforo LLM**: verde = cargado; **ámbar = descargado a propósito**, se carga solo en la siguiente etapa de texto; rojo = declarado como externo y no responde.
- **Modelo sin `comando`**: externo. Lo levantas tú y Loomcast no lo toca, como siempre: ni lo arranca ni lo para. Lo mismo si pones `autostart = false`.
- **Loomcast solo usa lo que puede parar.** Si encuentra un llama-server ya escuchando en la url de un modelo con `comando`, no arranca otro: **se hace cargo de ese** y lo para antes de la voz igual que si lo hubiera lanzado él. Al salir, en cambio, solo para lo que arrancó: eso era tuyo antes de que abriéramos.
- El historial del job dice **qué responde en el puerto y cuánto ocupa**, que puede no ser el modelo que marca el selector: tus scripts comparten el 9876, y ahí está la explicación de un guion escrito por un modelo que no habías elegido.
- Si Loomcast muere de golpe (SIGKILL, cuelgue), al volver a arrancar **recupera la RAM** del llama-server que dejó huérfano (`logs/llm.pid`).
- `inactividad_s` descarga el modelo tras un rato sin usarse, aunque no haya llegado ninguna etapa de GPU.
- `max_tokens` ([llm] o por modelo) tiene que dar para la etapa más larga, que es el guion. Si se queda corto, la respuesta llega cortada a media frase y Loomcast lo dice tal cual, con el valor que había y por dónde se quedó.

### Antes de lanzar un modelo se comprueba que cabe

`memoria_gb` ([llm] o por modelo) son los GiB de memoria unificada libres que
hacen falta para cargarlo. No reserva nada: es la condición que se comprueba
justo antes de lanzarlo. Loomcast pide el `/free` a ComfyUI, **espera a ver la
memoria de verdad** (el POST vuelve en 1 ms sin haber soltado nada; ver
"`POST /free` sí suelta con `--gpu-only`…"), repite la petición si no baja y,
si aun así no llega, el job sale como error contando la medición en vez de
arrancar el modelo.

Lo mismo, con dos diferencias, antes de una etapa que carga su modelo **dentro
del backend** (Qwen3-TTS, whisper): los GiB son `[cola].memoria_modelo_gb` y la
etapa corre igual si no llegan, porque son 4 y caben casi siempre — lo que hace
falta ahí es no cargarlos encima de algo que está a punto de irse al swap, y que
el historial lo diga si pasa. Antes no había ninguna puerta en ese lado: la voz
cargaba el TTS sobre lo que hubiera dentro.

### Los topes del asignador de MPS (lo que mandaba la voz al swap)

`[voz].mps_tope` y `mps_tope_bajo` son fracciones de la memoria que Metal
recomienda (`torch.mps.recommended_max_memory()`, 37,4 GiB en un M3 Max de 48).
Al cruzar el alto, el asignador de PyTorch suelta lo que tenía cacheado hasta
bajar del bajo.

No es un ajuste fino. El asignador de MPS cachea los bloques que libera, y en
una generación autorregresiva cada paso pide una forma un poco distinta de la
del anterior: no puede reutilizar nada y le pide a Metal un bloque nuevo cada
vez, mil veces seguidas. Medido narrando el guion de un episodio en un proceso
a solas, sin LLM ni ComfyUI dentro:

| | texto | audio | pico MPS | swapouts | tiempo |
|---|---|---|---|---|---|
| sin topes | 200 palabras | 93,4 s | **53,1 GiB** | +76,2 GiB | 212 s |
| con topes | 200 palabras | 88,8 s | **15,6 GiB** | +0,0 GiB | 95 s |
| con topes | 400 palabras | 185,3 s | **16,3 GiB** | +0,3 GiB | 204 s |

El pico no era el modelo (1,7B en fp16 son 4,7 GiB cargado) ni crecía con la
longitud del guion: crecía con el número de pasos. Con los topes puestos queda
plano en ~16 GiB por largo que sea el texto, no hay swap y tarda la mitad.

Se exportan desde `backend/config.py` con `setdefault`, porque torch los lee al
inicializar el asignador y en todo el backend `import torch` va dentro de las
funciones. Si los exportas tú, manda lo tuyo.

El antes/después queda en el log del job, o sea en el historial de la UI:

```
Memoria para «Qwen3.6 35B A3B (MLX)» (22 GiB): 16.4 → 27.0 GiB libres
(+10.6 en 1.7 s, 1 petición a /free)
```

El 22 de serie está medido en un M3 Max de 48 GiB: con Z-Image dentro quedan
16,4 GiB libres (no basta para un MLX de ~20 GiB) y en cuanto ComfyUI suelta
sube a 27,0 (sobra). Con otro equipo, ajústalo a lo que tus modelos necesiten de
verdad — ponerlo demasiado alto hace fallar jobs que habrían ido bien, y
demasiado bajo devuelve el `Killed: 9`.

Si ComfyUI no responde no se bloquea nada: un ComfyUI caído no retiene memoria,
y Loomcast se usa también sin él (`--sin-comfy`).

## Banco de voces

Voces reutilizables generadas con Qwen3-TTS VoiceDesign, guardadas en `voces/<slug>/ref.wav`. Cada proyecto elige una; la narración se produce clonando ese clip. Sembrar 6 de arranque: `./.venv/bin/python scripts/sembrar_voces.py`. Crear más desde la UI describiendo cómo debe sonar.

El banco es el **único** almacén de voces: también las de los personajes salen
de aquí (ver abajo). Una voz del banco ya se escucha, se reutiliza entre vídeos
y se borra desde un sitio, así que un segundo almacén en paralelo para el
reparto solo duplicaría ese trabajo. Borrar una voz deja sin ella a los tres que
podían estar usándola —el proyecto que narraba con ella, el personaje que decía
sus líneas y el miembro del reparto propio que se la llevaba a los vídeos
nuevos—, porque una referencia colgada a un `ref.wav` que ya no está no falla:
enmudece.

### Voz por personaje

La narración ya no es forzosamente una sola voz. El guion se parte en **tramos**
y cada uno se sintetiza con la voz que le toca: el narrador lleva la historia y
los personajes del reparto dicen sus líneas con la suya. El narrador sigue
siendo el que cuenta; no es un diálogo por turnos.

**Se activa por plantilla.** El formato del guion lo decide `formato_guion` en
`plantilla.json`, que ya tenía dos valores y ahora tiene tres:

| `formato_guion` | cuerpo del guion | quién lo usa |
|---|---|---|
| `frases` (por defecto) | `frases: [...]` | `curiosidades` |
| `narracion` | `narracion: "…"` | `drama`, `historia` |
| `lineas` | `lineas: [{personaje, texto}, …]` | `serie` |

`lineas` es para las **series**, donde un personaje recurrente tiene que sonar
igual en diez episodios. Las otras tres plantillas no lo declaran y su salida no
cambia: `guiones_repo.tramos()` devuelve para ellas **un solo tramo**
con el texto completo, o sea la misma llamada única al modelo de antes. Hay un
test por plantilla que lo fija.

Lo que se oye y lo que leen las demás etapas no cambia de forma: `texto_narrado()`
sigue devolviendo el texto seguido (sin marcas de quién habla), que es lo que
consumen las escenas, el brief musical y los metadatos. Los subtítulos y la
segmentación de escenas trabajan sobre el audio final, así que varias voces no
las descuadran: Whisper transcribe lo que de verdad se oye.

Tres decisiones que explican el resto:

- **La voz de un personaje es una voz del banco**, y quien habla y no tiene
  ninguna la recibe **al generar la narración**, sin pulsar nada: la etapa de voz
  se la escribe con VoiceDesign desde su **propia ficha**, que es de donde ya sale
  su retrato (dice la edad aparente, el género y el aire, que es justo lo que
  decide el timbre), y la deja asignada, así que regenerar la narración no la
  vuelve a escribir. El `instruct` se redacta con los cuatro bloques que
  VoiceDesign interpreta bien ([PERFIL DE VOZ], [EMOCIÓN Y ACTITUD], [DINÁMICA Y
  RITMO], [INDICACIONES DE CONTEXTO]) y es un punto de partida: la voz queda en
  el banco como cualquier otra, se cambia por otra en el selector del paso de Voz
  y se rehace con «Crear desde su ficha». El VoiceDesign se carga **una vez para
  todas** las que haya que escribir, no una por personaje. Quien no tenga ficha
  se queda sin voz propia: sus líneas las dice la del proyecto.
- **La voz viaja con el reparto propio**, igual que la ficha y la cara: se lleva
  al promover y al actualizar, y entra con el personaje al traerlo a un vídeo
  nuevo. Pero **no se copia** como el retrato —es una fila del banco, ya
  compartida entre vídeos—, así que si se borró del banco el personaje entra sin
  voz en vez de apuntar a un clip que no está. Regenerar el casting tampoco la
  pierde: elegirle voz es una decisión del usuario, no algo que el LLM reescriba.
- **El modelo se carga una vez por grupo de tramos, no uno por tramo.** En esta
  máquina cargar Qwen3-TTS cuesta más que sintetizar un tramo corto y el modelo
  no cabe dos veces en la memoria unificada. Se cargan como mucho dos, uno
  después de otro: VoiceDesign si el narrador va en modo expresivo, y Base para
  los clones. Y el prompt de clonado se construye una vez por voz distinta, no
  una por tramo.

Un tramo que falla no tira la narración entera: se queda fuera del audio, el log
del job dice cuál y por qué, y los subtítulos salen de lo que de verdad se oye.
Si fallan todos, la etapa falla —un `voz.wav` vacío lo darían por bueno los
subtítulos y el montaje—. Un personaje cuya voz todavía se está generando o
perdió su clip no deja un hueco: esa línea la narra la voz del proyecto. Una que
**falló** sí se rehace en la siguiente pasada: una voz muerta pegada al
personaje no suena y además taparía el hueco, así que se borra del banco y se le
escribe otra.

Y el **nombre del personaje no se narra**. El prompt del guion prohíbe escribirlo
delante de la frase y el LLM lo cuela igual; lo que se queda en el texto se oye,
porque el TTS dice lo que hay. `dueño_y_texto()` decide de una vez quién dice la
línea y qué dice, y lo usan los tres caminos: el guion que se guarda, el que lee
el editor y los tramos que se narran —esto último recoge los guiones que ya
estaban guardados con el nombre dentro—. Dos casos:

- **La línea tiene dueño y además lleva su nombre delante** ("ANA" / "ANA ¿Y si
  soy yo la que no existe?"): se quita el nombre. Solo el de *su* dueño y solo
  cuando viene como etiqueta —en mayúsculas igual que la clave, o seguida de dos
  puntos o raya—, porque una línea del narrador que empieza por "Ana decide
  borrar la mentira" no lleva etiqueta, lleva a Ana de sujeto.
- **La línea no tiene dueño y el nombre es lo único que dice quién habla** ("" /
  "ANA: Es una broma"): el nombre pasa al campo que le tocaba. El LLM redacta el
  cuerpo en formato teatro en vez de rellenar `personaje` —se lo pide el prompt y
  lo ignora—, y entonces fallan las dos cosas a la vez: nadie dice la línea, así
  que la narra el narrador, y encima el nombre se oye. Con dos puntos basta una
  inicial mayúscula; sin ellos el nombre tiene que venir en MAYÚSCULAS y lo que
  sigue arrancar como una frase dicha, para que un énfasis del narrador ("ESTO no
  es de dentro") no se convierta en un personaje.

Como el texto narrado no lleva marcas de quién dice cada cosa, al casting se le
pasan aparte las claves de quien tiene líneas, con la orden de devolverlas tal
cual: sin eso, un personaje que solo existe porque habla no tendría ficha, y sin
ficha no hay de dónde escribirle la voz.

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
- ✅ **Música de la historia** — el proyecto compone su pista desde el guion y las escenas, se descarga sola (audio sin narración, reutilizable en redes) y opcionalmente se mezcla bajo la voz con ducking
- ✅ **Cola con reintentos y parada** — los fallos transitorios se reintentan solos con espera creciente, y la generación se puede detener (lo que corre, la cola entera o las dos) desde la cabecera y desde las tres secciones
- ✅ **Plantilla `historia`** — un hecho real contado como relato: guion narrativo, voz grave y pausada, reparto y estilo de época sin personajes reconocibles. Tercer nicho junto a `curiosidades` y `drama`, y con ella se cierra la Fase 5
- ✅ **Reparto propio** — personajes guardados aparte, con su ficha y su cara, que se traen a cualquier vídeo nuevo; la cara se copia al proyecto y editarla ahí no toca al original. Primera pieza de la Fase 6
- ✅ **Voz por personaje** — la narración se sintetiza por tramos y cada personaje dice sus líneas con su voz del banco, que viaja con él en el reparto propio; el formato de guion con líneas atribuidas se activa por plantilla y hoy no lo usa ninguna (es para las series). Segunda pieza de la Fase 6
- ✅ **Series** — episodios con continuidad: reparto fijo que viaja a cada capítulo, resumen del episodio anterior como contexto del guion siguiente, plantilla `serie` con guion de líneas atribuidas y marca «SERIE · EP n» en el vídeo. Cierra la Fase 8
- ✅ **Autopiloto y lotes** — un proyecto va solo de donde esté hasta su `final.mp4`, parando en las tres revisiones de siempre (configurables, y desactivables para producción sin manos), y varias ideas de un tema se producen una detrás de otra; lo que se pide a mano adelanta en la cola, parar apaga las tiradas enteras y un vídeo que falla no tira los demás. Cierra la Fase 9
- ⬜ Pendiente — empaquetado

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
| **Qwen-Image-Edit 2511** | — | ✅ | GGUF + text encoder qwen2.5-vl, para esquivar el fp8 que Metal no soporta. Hasta 3 referencias, y el que usa el pipeline para las escenas con personaje. ~2 min por imagen |
| **FLUX.2 Klein 9B** | ✅ | ✅ | GGUF Q8 + encoder fp4mixed. ~50 s generando, ~76 s editando |

Qwen-Image-Edit 2511 son cuatro ficheros en `ComfyUI/models/` (Apache 2.0):

    diffusion_models/  qwen-image-edit-2511-Q4_K_M.gguf                        (13,24 GB, unsloth/Qwen-Image-Edit-2511-GGUF)
    loras/             Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors  (0,85 GB, lightx2v/Qwen-Image-Edit-2511-Lightning)
    text_encoders/     qwen2.5-vl-7b-test-q4_0.gguf
    vae/               qwen_image_vae.safetensors

El Lightning es lo que deja la edición en 4 pasos en vez de 40; sin él, el
workflow tarda diez veces más.

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
python scripts/instalar_parches.py
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

Agnóstico al motor: cada uno se declara en `config.toml [i2v.motores.*]`
apuntando a un workflow de ComfyUI **en formato API** que tú exportas y ajustas
(LTX, HunyuanVideo, WAN, etc.). Requisitos del workflow:

- Incluir los placeholders `{IMAGE}` (nombre del archivo subido), `{PROMPT}` (prompt de la escena), `{SEED}` y `{FRAMES}` en los valores de sus nodos.
- Terminar en un nodo que guarde video (`VHS_VideoCombine` o `SaveVideo`).

`frames` y `fps_origen` van **en cada motor**, no en `[i2v]`: son propiedad del
modelo. Pedirle a Hunyuan los 25 cuadros de LTX le costaría ~360 s por escena en
vez de 303, y un modelo que entregue a 16 fps cambiaría lo que interpola RIFE.

**El motor se elige en el paso de vídeo**, junto al modo; `[i2v].motor` fija cuál
viene preseleccionado. Cada escena guarda en qué motor se hizo su clip, así que
cambiar de motor rehace las escenas afectadas y volver al anterior las respeta,
igual que ya pasaba al cambiar de modo. Los clips anteriores a que se registrara
el motor cuentan como desconocidos y se rehacen.

Vienen declarados dos. El preseleccionado es **LTX-2.5** (22B destilado en GGUF
Q4_0), que el 2026-10-12 sustituyó a HunyuanVideo 1.5 como motor por defecto.
Medido en el M3 Max con la misma imagen, prompt y semilla, en caliente y a 8
pasos:

| motor | resolución | cuadros | tiempo |
|---|---|---|---|
| **LTX-2.5** | 480×864 | 25 | **90 s** |
| **LTX-2.5** | 768×1376 | 25 | **213 s** |
| HunyuanVideo 1.5 | 480×848 | 21 | 303 s |

LTX se usa a 768×1376, que es la resolución de las imágenes de escena: cuesta
menos que lo que tardaba Hunyuan a 480 y el armado tiene que estirar mucho menos
para llegar a 1080×1920. Para cambiarla, el nodo `ResolutionSelector` del
workflow.

Su text encoder va **en CPU** (`"device": "cpu"` en el `CLIPLoader`), como los
workflows de imagen. En GPU competía con el DiT: ComfyUI lo soltaba para hacer
sitio al muestreo y lo recargaba en la escena siguiente, y ese ir y venir de
14,6 GB disparaba el swap a 18 GB. En CPU se queda en 0,6 GB y cada clip baja
unos 8 s.

Un aviso por si mides esto: en macOS **`Pageouts` de `vm_stat` no es el swap**.
Lo que cuenta es `Swapouts`; con `Pageouts` parece que no pagina nunca.

**Hunyuan sigue disponible** como segundo motor: es más rápido a resoluciones
bajas, y tenerlo permite comparar movimiento escena a escena sin tocar ficheros.
Su text encoder tiene que ser el fp16, no el fp8_scaled: Metal no implementa
`Float8_e4m3fn`.

Los ficheros van a `ComfyUI/models/`:

    diffusion_models/  ltx-2.5-22b-distilled-transformer-Q4_0.gguf                 (12,51 GB, molbal/LTX-2.5-GGUF)
    text_encoders/     gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors (15,37 GB, Lightricks/LTX-2.5)
    vae/               ltx-2.5-video-vae-bf16.safetensors                          ( 1,47 GB, Lightricks/LTX-2.5)
    vae/               ltx-2.5-audio-vae-bf16.safetensors                          ( 0,36 GB, Lightricks/LTX-2.5)

El repo de Lightricks es *gated*: hay que aceptar la licencia con una cuenta de
Hugging Face y hacer `hf auth login` antes de descargar. El text encoder es un
**Gemma 4 12B**, más grande que el propio transformer.

**Necesita el parche del GGUF** (`python scripts/instalar_parches.py`): el
fichero de molbal trae `keyframes_abs_pos_embedding` cuantizado siendo un
parámetro suelto, y sin dequantizarlo ComfyUI no carga el modelo.

LTX genera también una pista de audio, porque es un modelo audio-vídeo. Loomcast
no la usa: el ffmpeg que escala el clip ya pasa `-an` y la banda sonora sale de
la voz y de `[musica]`.

Por cada escena, Loomcast sube la imagen, ejecuta el workflow, interpola el clip con **RIFE** (`config.toml [i2v].fps_origen`→`fps_final`) y lo ajusta a la duración del segmento de voz. Luego el armado con movimiento superpone subtítulos y voz. RIFE usa `rife-ncnn-vulkan` (Fase 0) por GPU; ajusta su ruta en `config.toml [rife]`.
