"""Cola de jobs en un hilo: las etapas LLM/GPU corren una a la vez."""
import json
import queue as _queue
import threading
import traceback

from ..db import get_session
from ..repositories import jobs as jobs_repo
from ..services import llm_runtime, progreso
from ..services.pipeline import (
    armado,
    armado_estatico,
    casting,
    clips,
    crear_voz,
    escena_individual,
    escenas,
    i2v,
    imagen_libre,
    imagenes,
    musica,
    quitar_fondo,
    retratos,
    subtitulos,
    texto,
    upscale,
    voz,
)

HANDLERS = {
    "generar_ideas": texto.generar_ideas,
    "generar_guion": texto.generar_guion,
    "generar_metadatos": texto.generar_metadatos,
    "crear_voz": crear_voz.crear_voz,
    "clonar_voz": crear_voz.clonar_voz,
    "generar_voz": voz.generar_voz,
    "generar_subtitulos": subtitulos.generar_subtitulos,
    "generar_casting": casting.generar_casting,
    "generar_retrato": retratos.generar_retrato,
    "generar_escenas": escenas.generar_escenas,
    "generar_imagenes": imagenes.generar_imagenes,
    "regenerar_imagen": imagenes.regenerar_imagen,
    "mejorar_prompt_imagen": imagen_libre.mejorar_prompt,
    "generar_previews_imagen": imagen_libre.generar_previews,
    "generar_final_imagen": imagen_libre.generar_final,
    "quitar_fondo": quitar_fondo.quitar_fondo,
    "mejorar_prompt_musica": musica.mejorar_prompt,
    "generar_musica": musica.generar,
    "generar_portada_musica": musica.generar_portada,
    "regenerar_clip": escena_individual.regenerar_clip,
    "generar_clips_mixto": escena_individual.generar_clips_mixto,
    "generar_upscale": upscale.generar_upscale,
    "generar_clips": clips.generar_clips,
    "generar_i2v": i2v.generar_i2v,
    "armar_video": armado.armar_video,
    "armar_estatico": armado_estatico.armar_estatico,
}

# Etapas que hablan con el llama-server. El resto (Qwen3-TTS, whisper, ComfyUI,
# ffmpeg) pelea por la misma memoria unificada, así que antes de cualquiera de
# ellas se descarga el LLM y así no compiten por la RAM.
JOBS_LLM = {
    "generar_ideas",
    "generar_guion",
    "generar_metadatos",
    "generar_casting",
    "generar_escenas",
    "mejorar_prompt_imagen",
    "mejorar_prompt_musica",
}

# Etapas que se disparan solas al terminar la anterior:
#  - voz → subtítulos (sin revisión intermedia)
#  - Ken Burns: upscale → clips → armado
#  - i2v: i2v → armado
#  - música: pista generada → portada
# Las escenas NO encadenan a imágenes: los prompts se revisan/editan primero.
CADENA = {
    "generar_voz": "generar_subtitulos",
    "generar_upscale": "generar_clips",
    "generar_clips": "armar_video",
    "generar_i2v": "armar_video",
    # La portada se hace DESPUÉS de la pista, no tras la sugerencia del LLM:
    # así solo la tienen las pistas que existen de verdad, y cada regeneración
    # estrena portada.
    "generar_musica": "generar_portada_musica",
    "generar_clips_mixto": "armar_video",
}

_cola: "_queue.Queue[int]" = _queue.Queue()


def encolar(tipo: str, ref_id: int, **params) -> int:
    """Encola un job. Los `params` extra se guardan en JSON y llegan al handler
    como kwargs: sirven para jobs que actúan sobre una escena concreta."""
    if tipo not in HANDLERS:
        raise ValueError(f"Tipo de job desconocido: {tipo}")
    with get_session() as s:
        job = jobs_repo.crear(s, tipo, ref_id, json.dumps(params))
        s.commit()
        job_id = job.id
    _cola.put(job_id)
    return job_id


def _procesar(job_id: int) -> None:
    with get_session() as s:
        job = jobs_repo.obtener(s, job_id)
        jobs_repo.marcar_corriendo(s, job)
        s.commit()
        tipo, ref_id = job.tipo, job.ref_id
        params = json.loads(job.params or "{}")
    progreso.iniciar(job_id, tipo)
    try:
        if tipo in JOBS_LLM:
            with llm_runtime.en_uso():
                estado, log = "ok", HANDLERS[tipo](ref_id, **params)
        else:
            llm_runtime.liberar(f"empieza {tipo}")
            estado, log = "ok", HANDLERS[tipo](ref_id, **params)
    except Exception:
        estado, log = "error", traceback.format_exc(limit=5)
    finally:
        progreso.limpiar()
    with get_session() as s:
        jobs_repo.finalizar(s, jobs_repo.obtener(s, job_id), estado, log)
        s.commit()
    # Las regeneraciones de una sola escena no encadenan: rearmar el video
    # entero en cada retoque costaría más que el propio retoque.
    if estado == "ok" and tipo in CADENA:
        encolar(CADENA[tipo], ref_id)


def _loop() -> None:
    while True:
        _procesar(_cola.get())


def arrancar_worker() -> None:
    threading.Thread(target=_loop, daemon=True, name="loomcast-worker").start()


def recuperar_pendientes() -> None:
    """Re-encola jobs que quedaron a medias si el server se reinició."""
    with get_session() as s:
        pendientes = jobs_repo.activos(s)
        for j in pendientes:
            j.estado = "pendiente"
        s.commit()
    for j in pendientes:
        _cola.put(j.id)
