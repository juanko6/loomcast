"""Etapa 5.5 — CASTING: quién sale en el vídeo y qué aspecto tiene.

Cada escena se prompt-ea por separado (ver escenas.py), así que el LLM no
recuerda lo que escribió en la anterior: el mismo personaje sale "a young woman"
en una escena y "a woman in her thirties" en otra, y el generador dibuja a dos
personas distintas. Aquí se le pide una vez la ficha física de cada personaje
recurrente, y luego esa ficha se pega **literal** en cada prompt donde aparezca.

Que sea literal es el punto: si se deja que el LLM la parafrasee en cada escena,
el personaje vuelve a derivar, solo que más despacio.

El reparto vacío es una respuesta válida y normal (curiosidades casi siempre).
"""
import json
import random
import re

from ...clients import llm
from ...db import get_session
from ...repositories import guiones as guiones_repo
from ...repositories import personajes as personajes_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...schemas import CastingLLM


def _limpiar_ficha(ficha: str) -> str:
    """Deja la ficha como una frase nominal continua, que es como se sustituye.

    El prompt lo pide, pero el modelo a veces devuelve varias frases ("…hazel
    eyes. She has a sharp jawline and wears…"), y eso pegado dentro de un
    prompt de escena queda partido a la mitad. Los puntos intermedios pasan a
    comas y se quitan los arranques de frase con pronombre, que es lo que los
    seguía.
    """
    t = " ".join(ficha.split()).rstrip(" .")
    t = re.sub(r"\.\s+(?:She|He|They|It)\s+(?:has|have|is|are|wears|wear)\s+", ", ", t)
    return re.sub(r"\.\s+", ", ", t)


def generar_casting(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        plantilla = p.plantilla

    g = json.loads(guion_row.contenido)
    guion_texto = guiones_repo.texto_narrado(g)

    pl = plantillas_repo.cargar(plantilla)
    system = pl["prompts"].get("casting")
    if system is None:
        raise ValueError(
            f"La plantilla '{plantilla}' no tiene prompts/casting.md; "
            "sin él no se puede fijar el reparto."
        )
    user = (
        f"Full video context:\n```markdown\n{guion_texto}\n```\n\n"
        f"Template visual style: {pl['estilo_visual']}"
    )
    r = llm.chat(system, user, CastingLLM)

    # Claves repetidas o vacías tras normalizar harían que dos personajes
    # compartieran marcador y se pisaran al sustituir.
    filas, vistas = [], set()
    for pj in r.personajes:
        clave = personajes_repo.normalizar_clave(pj.clave)
        if not clave or clave in vistas:
            continue
        vistas.add(clave)
        filas.append({
            "orden": len(filas),
            "clave": clave,
            "nombre": pj.nombre.strip(),
            "ficha": _limpiar_ficha(pj.ficha),
            "seed": random.randint(0, 2**31 - 1),
        })

    with get_session() as s:
        personajes_repo.reemplazar_todos(s, proyecto_id, filas)
        s.commit()

    if not filas:
        return "Sin personajes recurrentes: las escenas irán sin reparto fijo"
    nombres = ", ".join(f["clave"] for f in filas)
    return f"{len(filas)} personajes fijados ({nombres})"
