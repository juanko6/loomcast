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

Capas (de HTTP hacia abajo): `routers/` (controllers: validación y JSON, cero lógica) → `services/` (reglas de negocio; `services/pipeline/` son las etapas de generación) → `repositories/` (consultas a SQLite y carga de plantillas) → `models.py` (ORM + máquina de estados). Transversales: `clients/` (adaptadores a llama-server y Qwen3-TTS), `workers/queue.py` (cola de jobs en un hilo, uno a la vez, con encadenado, recuperación y reintentos), `services/progreso.py` (por dónde va el job en curso), `parada.py` + `services/cancelacion.py` (la bandera de parada y el corte en caliente del job que corre), `schemas.py` (contratos Pydantic de la API).

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

**La síntesis de voz no se puede cortar por dentro**: Qwen3-TTS es una sola
llamada a PyTorch sin puntos de control. Esas etapas (`generar_voz`, `crear_voz`
y la transcripción de `clonar_voz`) se paran antes de empezar, y si ya estaban en
marcha terminan: el audio vale, no se encadena la etapa siguiente y el log del
job lo dice. La UI tampoco promete lo que no puede hacer: el job expone
`sin_corte` (de `cancelacion.SIN_CORTE`) y el botón avisa en la confirmación de
que esa etapa se parará en cuanto acabe.

Un job parado **no encadena** la etapa siguiente, ni siquiera si el handler llegó
a terminar justo antes del corte: encadenar sería lo contrario de lo que se
pidió. Y el archivo a medio escribir se borra (`_ffmpeg.sin_restos`): un clip o
un `final.mp4` truncado existe en disco, y el resto del pipeline lo daría por
hecho —`ffmpeg concat` se salta sin fallar el clip que no puede abrir y
entregaría un vídeo al que le falta una escena—. En el historial, `cancelado` es
un estado propio y se lee «Parado», distinto de «Error»: pararlo fue una
decisión, no un fallo.


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
  que rehacerle la cara «con el mismo seed» en otro vídeo dé la misma persona.
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
- **Modelo sin `comando`**: externo. Lo levantas tú y Loomcast no lo toca, como siempre. Lo mismo si pones `autostart = false`.
- Si encuentra un llama-server ya escuchando en la url del modelo, lo **adopta** en vez de arrancar otro, y no lo para al terminar: puede ser tuyo.
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
