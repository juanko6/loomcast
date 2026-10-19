# Playbook: añadir una feature nueva a Loomcast

Guía para implementar una feature autocontenida (una "sección" de la app, como
la **Galería de imágenes** o la **Música**) siguiendo el patrón ya establecido.
Está pensada tanto para humanos como para agentes que retomen el proyecto.

Caso de referencia real: la sección **Música** (ACE-Step vía ComfyUI). Los
commits `66a63fc` (galería) y `b9f32f1` (música) son ejemplos completos.

---

## 1. Arquitectura en capas

Loomcast separa responsabilidades en capas estrictas. El trabajo pesado (LLM,
GPU/ComfyUI, ffmpeg) **nunca** corre en el hilo HTTP: se encola en una cola de
jobs de un solo hilo.

```
Frontend (vanilla JS)  ──HTTP──▶  Router (FastAPI)
                                     │  valida entrada, traduce excepciones → HTTPException
                                     ▼
                                  Service            ← cara HTTP: abre sesión, delega, encola
                                     │
                        ┌────────────┴────────────┐
                        ▼                          ▼
                  Repository (ORM)          workers/queue (cola de jobs, 1 hilo)
                        │                          │
                        ▼                          ▼
                  Model (SQLAlchemy)      services/pipeline/<feature>.py  ← etapas pesadas
                                                   │
                                                   ▼
                                          clients/ (comfy, llm, tts, fondo…)
                                                   │
                                                   ▼
                                          servicios externos (ComfyUI, llama-server)
```

Principios:
- **Router**: fino. Valida, llama al service, convierte `XNoExiste` → `HTTPException(404)`.
- **Service**: lo que atiende directo a la API (crear fila, listar, detalle, borrar) y
  **encola** los jobs. No hace trabajo pesado.
- **Repository**: helpers ORM que reciben `Session` como primer argumento. **No** hacen commit
  (lo hace el service).
- **Model**: tabla SQLAlchemy 2.0 (`Mapped[...] = mapped_column(...)`). El ciclo de vida vive
  en una columna `estado` (string). Los binarios (audio, imágenes, vídeo) van **en disco**, no
  en la DB.
- **Pipeline**: los handlers de la cola. Aquí y solo aquí se llama a `clients/*`.
- **Clients**: adaptadores a servicios externos. `comfy.py` habla con ComfyUI; `llm.py` con
  llama-server.

DB: **SQLite** (`loomcast.db`), engine con `check_same_thread=False` (API y worker en hilos
distintos). Una tabla nueva se crea sola con `Base.metadata.create_all` en `init_db()` — basta
importar el modelo en `models/__init__.py`. Solo hace falta migración manual (`_migrar()` en
`db.py`) al **añadir columnas** a una tabla existente.

---

## 2. Checklist para una feature respaldada por ComfyUI

Orden recomendado (backend → wiring → frontend → prueba). Entre paréntesis, el archivo
equivalente de la feature de música como plantilla.

### Backend
1. **Modelo** `backend/models/<feature>.py` — clase `Base`, `__tablename__`, columna `estado`.
   Registrar en `backend/models/__init__.py` (import + `__all__`). (`models/musica.py`)
2. **Repository** `backend/repositories/<feature>.py` — `crear/obtener/listar/…/borrar`, cada
   uno recibe `Session`, sin commits. (`repositories/musica.py`)
3. **Schemas API** en `backend/schemas/api.py` — clases `…In` (Pydantic), exportar en
   `schemas/__init__.py`. Si el LLM interviene, **schema de salida** en `schemas/llm.py`. (`MusicaGenerarIn`, `MusicaPromptLLM`)
4. **Cliente** — añadir la función a `backend/clients/comfy.py` (ver §3). (`comfy.generar_musica`)
5. **Pipeline** `backend/services/pipeline/<feature>.py` — handlers de la cola. Envolver la
   llamada a ComfyUI en `try/finally: comfy.liberar_memoria()`. (`pipeline/musica.py`)
6. **Service** `backend/services/<feature>.py` — cara HTTP; declara `TIPOS_JOB`, excepción
   `XNoExiste`, `_a_dict` con `ocupado` (desde `jobs_repo.activos`). (`services/musica.py`)
7. **Router** `backend/routers/<feature>.py` — `APIRouter(prefix="/api/<feature>")`; incluye un
   `GET /{id}/<binario>` con `FileResponse(..., media_type=...)`. (`routers/musica.py`)
8. **Config** — sección `[<feature>]` en `config.toml` + constantes en `backend/config.py`
   (`X_WORKFLOW`, `X_DIR`). (`[musica]`, `MUSICA_WORKFLOW`, `MUSICA_DIR`)

### Wiring
9. **Cola** `backend/workers/queue.py` — importar el pipeline, registrar los handlers en
   `HANDLERS`; añadir los jobs LLM a `JOBS_LLM`; encadenados automáticos a `CADENA` si aplica.
10. **App** `backend/main.py` — importar el router y `app.include_router(<feature>.router)`.
11. **.gitignore** — añadir el directorio de salida (`<feature>/`) para no versionar binarios.

### Frontend (`frontend/app.js` + `index.html`)
12. Sección en el sidebar de `index.html` (lista + botón "nuevo").
13. En `app.js`: añadir la fetch a `cargarListas()`, una `render<Feature>(id)`, el dispatch en
    `renderVista()`, y los handlers en los listeners delegados (click / submit). El refresco al
    terminar un job es **automático** (`refrescarJobs` cada 2.5s re-renderiza al bajar el contador).

---

## 3. Convenciones clave de ComfyUI

### Workflows en formato API con placeholders
Los workflows viven en `workflows/*.json` en **formato API** de ComfyUI (dict plano
`node_id → {class_type, inputs}`, conexiones `["node_id", out_index]`). Se parametrizan con
tokens que `comfy.py` sustituye por texto antes de `json.loads`:

- **String** (dentro de comillas en el JSON): `"tags": "{TAGS}"` → se sustituye con
  `json.dumps(valor)[1:-1]` (escapa comillas/saltos, sin las comillas exteriores).
- **Numérico** (sin comillas): `"seed": {SEED}` → se sustituye con `str(int)`.

Alternativa (para valores propios, no de usuario): parsear el JSON y mutar el dict
(`wf["nodo"]["inputs"]["x"] = v`), como hace `generar_imagen`.

### Cómo obtener el JSON API de un workflow
ComfyUI **embebe** el grafo en los metadatos de cada salida, con la clave `prompt` (formato API,
justo el que necesitamos) y `workflow` (formato UI). Truco usado para la música: descargar una
salida de ejemplo (`.flac`/`.png`) y leer la clave `prompt` de sus metadatos (Vorbis comment en
FLAC / tEXt chunk en PNG). Así se evita reconstruir el grafo a mano. Luego se insertan los
placeholders en los campos que deban variar.

### Descarga de la salida
ComfyUI expone los archivos en `GET /view?filename=&subfolder=&type=`. Ya hay descargadores por
tipo en `comfy.py` (`_descargar_primera_imagen`, `_descargar_primer_video`,
`_descargar_primer_audio`). El de audio **conserva la extensión de origen** (FLAC/MP3/WAV) porque
el nodo de guardado lo decide el workflow.

### Liberar memoria (importante en Apple Silicon)
Tras **cada** etapa GPU, llamar a `comfy.liberar_memoria()` (`POST /free` con `unload_models` +
`free_memory`), dentro de un `finally`. Loomcast comparte la RAM unificada entre ComfyUI, el
llama-server y el TTS; si no se libera, compiten. La cola además descarga el LLM antes de
cualquier job que no sea de texto (ver `JOBS_LLM` / `llm_runtime`).

### LLM con salida estructurada
`llm.chat(system_prompt, user_text, SchemaPydantic)` restringe la generación con el JSON schema
del modelo Pydantic y valida la respuesta. Los prompts de sistema son archivos en `prompts/*.md`
(uno por variante; p. ej. `musica_instrumental.md` vs `musica_cancion.md`). Los jobs que usan el
LLM deben estar en `JOBS_LLM` para que se cargue el modelo bajo demanda.

---

## 4. Ejemplo concreto: la sección Música

- **Modelo**: ACE-Step 1.5 (ACE Studio + StepFun). Elegido sobre Meta MusicGen por generar
  **voz + letra**, licencia **Apache 2.0** (comercial), correr en **Metal/MPS** y tener soporte
  **nativo en ComfyUI**. Checkpoint `ace_step_v1_3.5b.safetensors` (~7.7 GB) en
  `~/Documents/ComfyUI/ComfyUI/models/checkpoints/`.
- **Dos modos** (columna `tipo`): `instrumental` (solo `tags`) y `cancion` (`tags` + `lyrics`
  con `[verse]`/`[chorus]`). Estado: `nueva → generada`.
- **LLM opcional**: botón "Sugerir con LLM" rellena tags/letra desde una idea; también se
  escriben a mano ("ambos disponibles").
- **Workflow** `workflows/musica_api.json`: placeholders `{TAGS}`, `{LYRICS}` (string),
  `{SEED}`, `{DURACION}` (numérico). Nodos: CheckpointLoaderSimple → TextEncodeAceStepAudio +
  ConditioningZeroOut → ModelSamplingSD3 + LatentApplyOperationCFG → KSampler (50 steps, cfg 5,
  euler/simple) → VAEDecodeAudio → SaveAudio (FLAC).
- **Rendimiento medido** (M3 Max 48GB): pista instrumental de 15 s en ~25 s incluyendo la carga
  del modelo. Sale en FLAC estéreo 44.1 kHz.

Prerequisitos manuales que quedan del lado del usuario (como con i2v/edición): descargar el
checkpoint y tener `workflows/musica_api.json` (ya incluido). Cambiar `SaveAudio` por
`SaveAudioMP3` en el workflow si se prefiere MP3 — el backend detecta la extensión solo.

---

## 5. Cómo probar una feature end-to-end

1. Arrancar ComfyUI (`.claude/launch.json` tiene la config `comfyui`) y confirmar que ve el
   checkpoint: `GET /object_info/CheckpointLoaderSimple`.
2. Arrancar el backend: `uvicorn backend.main:app --host 127.0.0.1 --port 8700`
   (usa `.venv/bin/uvicorn`). `LLM_AUTOSTART=0` para aislar la ruta de ComfyUI sin el LLM.
3. Probar la API con `curl` (crear → listar → detalle → generar) y sondear `estado`/`tiene_audio`.
4. Verificar la UI en el navegador (sección en el sidebar, render del detalle, sin errores de
   consola).
5. Confirmar que el binario se produce en disco y que el endpoint `GET /{id}/<binario>` lo sirve
   con el `media_type` correcto.
6. Al terminar, revisar que `liberar_memoria()` dejó la RAM libre.

> Nota Apple Silicon: `system_stats` de ComfyUI reporta la memoria unificada de **todo el
> sistema**, no solo lo que tiene cargado; que el número no suba +tamaño-del-modelo tras liberar
> es la señal de que se descargó. El asignador MPS de PyTorch mantiene un caché interno (memoria
> reutilizable, no es fuga).

---

## 6. Cuando la suite falla de forma intermitente

Pasó el 2026-10-19: una corrida dijo `2 failed, 599 passed` y las ocho siguientes
quedaron en verde, incluidas cinco con la máquina cargada a propósito (14 cores
quemando y 6 GB fijos, y luego bloques de 12 GB pidiéndose y soltándose de golpe,
que es lo que hace un modelo al cargar y descargar). La corrida que falló tardó
20 s en vez de 11,7, así que la lentitud se reprodujo; el fallo, no.

Dos cosas que aprender de ahí, porque costaron tiempo:

- **No filtres la salida de pytest a una línea.** `addopts = -ra` ya imprime el
  resumen de fallos con sus nombres; un `| tail -1` lo tira justo cuando hace
  falta. Si un fallo intermitente se pierde, no hay forma de recuperarlo.
- **`.pytest_cache/v/cache/lastfailed` NO es prueba de qué falló.** pytest
  reescribe las entradas de los tests que recolecta, pero **conserva las de los
  que ya no existen**, así que mezcla corridas viejas con la última. En ese
  incidente nombraba dos tests renombrados hacía días (uno en `52da77d`) y mandó
  la investigación a dos ficheros que no tenían nada que ver. Antes de creerla,
  comprueba que esos nombres se recolectan hoy:
  `pytest --collect-only -q | grep <nombre>`.

Si vuelve a pasar, el candidato con una fragilidad real es
`test_armar_video_con_clip_corrupto_falla_en_vez_de_entregar_un_video_incompleto`:
su `match` exige que la escena 1 sea la **única** corrupta, y `duracion()`
devuelve 0.0 también cuando el `ffprobe` se pasa de `SONDEO_S` (30 s), con lo que
un sondeo agotado en el clip bueno metería la escena 0 en el mensaje y el regex
no casaría. Son 30 s para sondear un clip de 0,5 s, así que haría falta un swap
muy severo; se deja escrito, no cambiado, porque relajar ese regex dejaría pasar
justo el bug del que es regresión.

---

## 7. Convenciones del proyecto

- Todo el código y los comentarios en **español**.
- Commits: **solo el usuario como autor** (sin `Co-Authored-By`). Un commit por feature; si el
  árbol tiene features entrelazadas, separar por commit (ver cómo se separó galería/música en el
  historial).
- Idempotencia de la cola: `recuperar_pendientes()` re-encola jobs a medias tras un reinicio.
- Los binarios de salida (`proyectos/`, `galeria/`, `musica/`) están en `.gitignore`.
