"""Etapa opcional — MÚSICA DEL PROYECTO: la banda sonora de esta historia.

Dos cosas la separan de la sección de Música, donde el usuario escribe una idea
suelta:

  1. **El brief sale de la historia.** El LLM lee el guion narrado y los planos
     de las escenas y escribe el estilo, el tempo, la tonalidad y el guion de
     secciones para ESTE video, con la duración que dura la narración. Una cama
     genérica valdría para cualquier vídeo; eso es justo lo que no se quiere.

  2. **La pista se entrega sola.** No se incrusta y punto: nace como una fila de
     `musicas` y vive en la biblioteca igual que las demás, así que se escucha,
     se descarga y se reutiliza en redes como audio sin narración. Que además se
     mezcle bajo la voz en el video final es un interruptor aparte
     (`Proyecto.musica_mezclar`), que mira el armado.

La síntesis no se reimplementa: es la misma de la sección de Música. Lo que sí
es de aquí es **quién la pide**: el brief habla con el LLM y la síntesis con
ComfyUI, y en esta máquina los dos modelos no caben a la vez, así que son dos
jobs y no uno. Entre job y job es la cola quien descarga el llama-server, que
es el único sitio donde eso está escrito una vez.

Los dos llevan el id del proyecto, y eso es lo que los hace etapas del vídeo:
van encadenados en la cola como voz → subtítulos, y lo que termina habla de su
proyecto, así que el autopiloto lo sigue sin saber nada de pistas. La portada
se encola al final con el id de la pista, porque es de la pista y nadie la
espera para montar el vídeo.
"""
import json
import math

from ... import parada
from ...clients import llm
from ...config import MUSICA_DURACION_S, PROYECTOS_DIR, VIDEO_COLA_FINAL_S
from ...db import get_session
from ...repositories import escenas as escenas_repo
from ...repositories import guiones as guiones_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import musica as musica_repo
from ...repositories import proyectos as proyectos_repo
from ...schemas import MusicaPromptLLM
from ..musica_combos import (
    normalizar_bpm,
    normalizar_idioma,
    normalizar_keyscale,
    normalizar_timesig,
)
from . import musica as musica_pipeline

# Cuánto de cada plano se le pasa al LLM. Lo que aporta el storyboard aquí es el
# ambiente, no el detalle del prompt de imagen, y los prompts enteros de doce
# escenas inflan la petición sin cambiar la música.
_PLANO_CHARS = 160


def _duracion_objetivo(base) -> int:
    """Lo que tiene que durar la pista: lo que dura la narración más la cola de
    imagen del final del video.

    Sin voz todavía (se pide la música antes de narrar) se cae a la duración por
    defecto de una pista: la narración es lo único que fija de verdad cuánto
    dura el video. Que la pista quede corta no rompe nada, la mezcla la rellena
    con silencio; si cambia mucho, se rehace la música.
    """
    import soundfile as sf

    voz = base / "voz.wav"
    if voz.exists():
        return math.ceil(sf.info(voz).duration + VIDEO_COLA_FINAL_S)
    return MUSICA_DURACION_S


def _contexto(titulo: str, guion_texto: str, planos: list[str], plantilla: str,
              duracion_s: int) -> str:
    bloque_planos = ""
    if planos:
        bloque_planos = "\n\nShots, in order:\n" + "\n".join(
            f"{i + 1}. {p}" for i, p in enumerate(planos)
        )
    return (
        f"Video title: {titulo or '(sin título)'}\n"
        f"Niche / template: {plantilla}\n\n"
        f"Narration script (Spanish, this is what the voice says):\n"
        f"```\n{guion_texto}\n```"
        f"{bloque_planos}\n\n"
        f"The track must last exactly {duracion_s} seconds.\n\n"
        'Answer with the JSON object only, starting with {"tags":'
    )


def generar_musica_proyecto(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía: la música se "
                             "escribe a partir de la historia")
        meta_row = metadatos_repo.ultimo(s, proyecto_id)
        slug, plantilla, musica_id = p.slug, p.plantilla, p.musica_id
        planos = [
            (e.prompt or e.texto or "")[:_PLANO_CHARS]
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]

    g = json.loads(guion_row.contenido)
    guion_texto = guiones_repo.texto_narrado(g)
    titulo = ""
    if meta_row:
        titulo = json.loads(meta_row.contenido)["youtube"]["titulo"]
    if not titulo:
        titulo = g.get("gancho", "")

    duracion_s = _duracion_objetivo(PROYECTOS_DIR / slug)
    sistema = musica_pipeline.leer_prompt("musica_proyecto.md")
    r = llm.chat(
        sistema,
        _contexto(titulo, guion_texto, [x for x in planos if x], plantilla, duracion_s),
        MusicaPromptLLM,
    )

    # La pista es instrumental siempre: lleva una narración encima y cualquier
    # voz cantada competiría con ella.
    campos = dict(
        tags=r.tags,
        lyrics=r.lyrics,
        duracion_s=duracion_s,
        bpm=normalizar_bpm(r.bpm),
        keyscale=normalizar_keyscale(r.keyscale),
        timesig=normalizar_timesig(r.timesig),
        idioma=normalizar_idioma("en"),
        portada=r.portada,
    )
    idea = f"Banda sonora de «{titulo}»" if titulo else f"Banda sonora de {slug}"

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        m = musica_repo.obtener(s, musica_id) if musica_id else None
        if m is None:
            # Primera vez: nace en la biblioteca de Música como una pista más.
            m = musica_repo.crear(
                s, "instrumental", idea, campos["tags"], campos["lyrics"],
                campos["duracion_s"], campos["bpm"], campos["keyscale"],
                campos["timesig"], campos["idioma"],
            )
            m.portada = campos["portada"] or None
            s.flush()
            p.musica_id = m.id
        else:
            # Rehacer la música del proyecto reescribe su pista en vez de
            # dejar una fila huérfana por intento.
            m.idea = idea
            m.tipo = "instrumental"
            musica_repo.guardar_campos(s, m, **campos)
            # Vuelve a "nueva" hasta que exista el audio del brief nuevo.
            m.estado = "nueva"
            # Seed nuevo: la pista anterior era de otro brief.
            m.seed = None
        s.commit()
        musica_id = m.id

    # La síntesis sale sola detrás de esta (`CADENA`), en su propio job y con
    # el mismo id de proyecto: así la cola descarga el LLM antes de que ComfyUI
    # pida la memoria, y hereda la prioridad de quien pidió la música.
    return (f"Brief musical escrito para «{titulo}» ({duracion_s} s, "
            f"{campos['bpm']} BPM, {campos['keyscale']}); pista #{musica_id} en cola")


def sintetizar_musica_proyecto(proyecto_id: int) -> str:
    """Sintetiza la pista que el brief dejó encargada.

    Es la síntesis de la sección de Música llamada con el id del proyecto. Dar
    el rodeo (un job de proyecto que llama a la pista) en vez de encolar
    `generar_musica` a secas es lo que mantiene la música dentro del flujo del
    vídeo: ese job lleva el id de la pista, y una etapa que termina hablando de
    otra cosa deja al autopiloto esperando algo que nunca le llega.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        musica_id = p.musica_id
    if musica_id is None:
        raise ValueError("El proyecto no tiene pista todavía: la escribe "
                         "«generar_musica_proyecto»")

    parada.comprobar("el brief musical ya estaba escrito")
    nota = musica_pipeline.generar(musica_id)

    # La portada va aparte y con el id de la pista: es de ella, es cosmética y
    # el vídeo no la espera.
    from ...workers import queue

    queue.encolar("generar_portada_musica", musica_id)
    return f"{nota} (pista #{musica_id})"
