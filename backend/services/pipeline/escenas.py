"""Etapa 6 — ESCENAS: segmentar la narración y generar prompts visuales.

Divide el audio en intervalos de ~duracion_escena_s (cortando en límites de
palabra según palabras.json) y pide al LLM dos prompts en inglés por escena —
el visual (para la imagen) y el de movimiento (para el modo i2v) —, con el
guion completo como contexto y el estilo de la plantilla.

Si el proyecto tiene reparto (ver casting.py), al LLM se le pide que referencie
a cada personaje con su marcador {CLAVE} en vez de describirlo, y aquí se
sustituye por su ficha literal. Así el mismo personaje llega al generador con
exactamente las mismas palabras en todas sus escenas.
"""
import json
import math
import random
import re

from ...clients import llm
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import guiones as guiones_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import personajes as personajes_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...schemas import EscenaLLM
from .. import progreso

# Cualquier marcador que sobreviva a la sustitución: o el LLM se inventó una
# clave que no existe, o escribió llaves por su cuenta.
_MARCADOR = re.compile(r"\{([^{}]*)\}")


def _segmentar(palabras: list[dict], duracion_escena_s: float) -> list[dict]:
    """Reparte las palabras en N intervalos de duración similar."""
    fin_audio = palabras[-1]["end"]
    n = max(1, math.ceil(fin_audio / duracion_escena_s))
    limites = [fin_audio * i / n for i in range(n + 1)]
    segmentos = []
    for i in range(n):
        del_intervalo = [
            w for w in palabras if limites[i] <= w["start"] < limites[i + 1]
        ]
        if not del_intervalo:
            continue
        segmentos.append({
            "t_inicio": round(limites[i], 3),
            "t_fin": round(limites[i + 1], 3),
            "texto": " ".join(w["word"].strip() for w in del_intervalo),
        })
    # El último segmento cubre hasta el final real del audio
    if segmentos:
        segmentos[-1]["t_fin"] = round(fin_audio, 3)
    return segmentos


def _breve(ficha: str) -> str:
    """Identificación corta del personaje: lo que va antes del primer detalle.

    "a woman in her early thirties with dark curls, warm brown eyes, …" →
    "a woman in her early thirties". Sirve para el prompt de movimiento, que
    debe caber en 25-45 palabras y solo necesita saber quién se mueve, no cómo
    es de la cabeza a los pies.
    """
    cabeza = re.split(r"[,;]| with | wearing ", ficha, maxsplit=1)[0].strip()
    palabras = cabeza.split()
    return " ".join(palabras[:8]) if palabras else ficha


def _aplicar_casting(prompt: str, fichas: dict[str, str],
                     breve: bool = False) -> tuple[str, list[str]]:
    """Cambia cada {CLAVE} por su ficha y devuelve el prompt y quién sale.

    Los personajes se deducen de las fichas que se sustituyeron de verdad, no
    de una lista aparte que declare el LLM: lo que cuenta es lo que acabó
    escrito en el prompt.
    """
    usados = []
    for clave, ficha in fichas.items():
        texto = _breve(ficha) if breve else ficha
        marca = "{" + clave + "}"
        if marca in prompt:
            prompt = prompt.replace(marca, texto)
            usados.append(clave)
        # El modelo a veces escribe la clave pelada ("MADRASTRA stands alone…"):
        # quería referenciarla y se dejó las llaves. Sin esto la escena no se
        # marca, se genera sin su cara, y al generador de imagen le llega la
        # palabra MADRASTRA, que no significa nada. Las claves van en mayúsculas
        # y en español, así que confundirlas con una palabra del prompt (en
        # inglés y en minúscula) no pasa.
        suelta = re.compile(r"\b" + re.escape(clave) + r"\b")
        if suelta.search(prompt):
            prompt = suelta.sub(texto, prompt)
            if clave not in usados:
                usados.append(clave)
    # Un marcador huérfano llegaría tal cual al generador de imagen, que lo
    # dibujaría como texto o lo tomaría por un dynamic prompt de ComfyUI. Se le
    # quitan las llaves y se deja dentro lo que hubiera.
    return _MARCADOR.sub(r"\1", prompt), usados


def detectar_personajes(prompt: str, fichas: dict[str, str]) -> list[str]:
    """Qué personajes del reparto salen en un prompt ya escrito.

    Los prompts se guardan con la ficha sustituida, así que quién sale se puede
    leer del propio texto. Hace falta al guardar prompts editados a mano: si
    metes a alguien en una escena (o lo quitas), lo que decidió el LLM al
    generarla deja de valer, y sin esto la escena seguiría generándose sin su
    cara. Se acepta también la forma abreviada, que es la que va en el prompt de
    movimiento.
    """
    return [
        clave
        for clave, ficha in fichas.items()
        if ficha and (ficha in prompt or _breve(ficha) in prompt)
    ]


def _bloque_casting(fichas: dict[str, str]) -> str:
    """Instrucción de reparto para el prompt de escena. Vacía si no hay."""
    if not fichas:
        return ""
    lista = "\n".join(f"- {{{clave}}}: {ficha}" for clave, ficha in fichas.items())
    return (
        "\n\nRecurring cast of this video:\n"
        f"{lista}\n\n"
        "When one of them is the subject of the current segment, refer to them "
        "in both prompts by writing their marker exactly as shown (including "
        "the braces) instead of describing their appearance. Each marker is "
        "replaced with the description above before the image is generated, so "
        "do not repeat, rephrase or contradict those physical details, and do "
        "not invent markers that are not in this list. Everything else — "
        "action, setting, framing, lighting, mood — you still write yourself. "
        "If the segment shows none of them, use no marker."
    )


def generar_escenas(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        meta_row = metadatos_repo.ultimo(s, proyecto_id)
        slug, plantilla = p.slug, p.plantilla
        fichas = personajes_repo.fichas(s, proyecto_id)

    palabras_path = PROYECTOS_DIR / slug / "palabras.json"
    if not palabras_path.exists():
        raise ValueError("No hay palabras.json; genera la voz y subtítulos primero")
    palabras = json.loads(palabras_path.read_text())

    g = json.loads(guion_row.contenido)
    guion_texto = guiones_repo.texto_narrado(g)
    titulo = ""
    if meta_row:
        titulo = json.loads(meta_row.contenido)["youtube"]["titulo"]

    pl = plantillas_repo.cargar(plantilla)
    segmentos = _segmentar(palabras, pl["ritmo"]["duracion_escena_s"])
    if not segmentos:
        raise ValueError("No se pudieron segmentar las palabras")

    system = pl["prompts"]["escena"]
    casting = _bloque_casting(fichas)
    escenas = []
    for i, seg in enumerate(segmentos):
        progreso.lote(i, len(segmentos), "escena")
        user = (
            f"Full video context:\n```markdown\n{titulo}\n{guion_texto}\n```\n\n"
            f"Current voice-over segment:\n```markdown\n{seg['texto']}\n```\n\n"
            f"Template visual style: {pl['estilo_visual']}"
            f"{casting}"
        )
        r = llm.chat(system, user, EscenaLLM)
        # El prompt se guarda ya sustituido: lo que se lee en la UI es lo que
        # se le manda al generador, y sigue siendo editable a mano.
        prompt, quienes = _aplicar_casting(r.prompt, fichas)
        movimiento, _ = _aplicar_casting(r.prompt_movimiento, fichas, breve=True)
        escenas.append(seg | {
            "orden": len(escenas),
            "prompt": prompt,
            "prompt_movimiento": movimiento,
            "personajes": ",".join(quienes),
            "seed": random.randint(0, 2**31 - 1),
        })

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        escenas_repo.reemplazar_todas(s, proyecto_id, escenas)
        avanzar_estado(p, "ESCENAS")
        s.commit()
    return f"{len(escenas)} escenas con prompt visual y de movimiento"
