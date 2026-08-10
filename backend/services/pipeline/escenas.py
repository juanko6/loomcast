"""Etapa 6 — ESCENAS: segmentar la narración y generar prompts visuales.

Divide el audio en intervalos de ~duracion_escena_s (cortando en límites de
palabra según palabras.json) y pide al LLM dos prompts en inglés por escena —
el visual (para la imagen) y el de movimiento (para el modo i2v) —, con el
guion completo como contexto y el estilo de la plantilla.
"""
import json
import math
import random

from ...clients import llm
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import guiones as guiones_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...schemas import EscenaLLM
from .. import progreso


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
    escenas = []
    for i, seg in enumerate(segmentos):
        progreso.lote(i, len(segmentos), "escena")
        user = (
            f"Full video context:\n```markdown\n{titulo}\n{guion_texto}\n```\n\n"
            f"Current voice-over segment:\n```markdown\n{seg['texto']}\n```\n\n"
            f"Template visual style: {pl['estilo_visual']}"
        )
        r = llm.chat(system, user, EscenaLLM)
        escenas.append(seg | {
            "orden": len(escenas),
            "prompt": r.prompt,
            "prompt_movimiento": r.prompt_movimiento,
            "seed": random.randint(0, 2**31 - 1),
        })

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        escenas_repo.reemplazar_todas(s, proyecto_id, escenas)
        avanzar_estado(p, "ESCENAS")
        s.commit()
    return f"{len(escenas)} escenas con prompt visual y de movimiento"
