"""Etapa 5.5 — CASTING: quién sale en el vídeo y qué aspecto tiene.

Cada escena se prompt-ea por separado (ver escenas.py), así que el LLM no
recuerda lo que escribió en la anterior: el mismo personaje sale "a young woman"
en una escena y "a woman in her thirties" en otra, y el generador dibuja a dos
personas distintas. Aquí se le pide una vez la ficha física de cada personaje
recurrente, y luego esa ficha se pega **literal** en cada prompt donde aparezca.

Que sea literal es el punto: si se deja que el LLM la parafrasee en cada escena,
el personaje vuelve a derivar, solo que más despacio.

El reparto vacío es una respuesta válida y normal (curiosidades a menudo; no
cuando la historia es la de un objeto concreto, que entonces es el protagonista).
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


# De qué es la ficha: una persona o un objeto. El reparto admite las dos cosas a
# propósito, pero su imagen de referencia se encuadra distinto, y pedirle cara,
# cabeza y piel a un mapa le pinta una cara encima.
#
# **No se confía en lo que diga el LLM.** Se le pide el campo, pero mlx_lm ignora
# el json_schema, así que llega vacío con la mitad de los servidores, y aun
# cuando llega se equivoca: en la base de este proyecto había un cofre, un
# Motorola DynaTAC, un robot y una entidad digital, los cuatro marcados
# "persona". Lo que sí es fiable es la propia ficha, porque el prompt de casting
# dicta qué lleva: para una persona, edad aparente, complexión, tono de piel,
# color de pelo y de ojos; para un objeto, forma, material y desgaste. Un cofre
# no tiene ojos y una viuda no está hecha de roble.
_NEGADO = re.compile(r"\bno (?:humans?|people|person|figures?|faces?)\b")
# Rasgos que solo se describen de alguien con cara.
_RASGOS = re.compile(
    r"\b(?:skin|hair|eyes?|beard|moustache|mustache|complexion|cheekbones|"
    r"jawline|eyebrows|lips|freckles|wrinkles|stubble)\b"
)
# La edad aparente, que el prompt pide para toda persona.
_EDAD = re.compile(r"\b(?:in (?:his|her|their)|years old|aged)\b")
_SUSTANTIVO = re.compile(
    r"\b(?:man|men|woman|women|boy|girl|male|female|child|children|person|"
    r"lady|gentleman|teenager|baby)\b"
)
# La cláusula de ropa con la que el prompt obliga a cerrar la ficha de una
# persona ("..., wearing a rumpled olive wool greatcoat"). Ninguna de las fichas
# de objeto de este proyecto la lleva, y salva los retratos escuetos donde no se
# describen rasgos.
_ROPA = re.compile(r"\bwearing\b")


def normalizar_tipo(tipo: str, ficha: str) -> str:
    """persona | objeto, deducido de la ficha.

    Las palabras completas importan: sin `\b`, "chair" trae "hair" y "human"
    trae "man". Con dos señales o más es una persona; con ninguna, un objeto; y
    con exactamente una (un retrato escueto, "a young diver in a wetsuit")
    desempata lo que haya dicho el LLM, que para eso se le pregunta.
    """
    f = (ficha or "").lower()
    if _NEGADO.search(f):
        return "objeto"
    señales = (
        len(set(_RASGOS.findall(f)))
        + (1 if _EDAD.search(f) else 0)
        + (1 if _SUSTANTIVO.search(f) else 0)
        + (1 if _ROPA.search(f) else 0)
    )
    if señales >= 2:
        return "persona"
    if señales == 0:
        return "objeto"
    return "objeto" if (tipo or "").strip().lower().startswith("obj") else "persona"


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
            "tipo": normalizar_tipo(pj.tipo, pj.ficha),
            "seed": random.randint(0, 2**31 - 1),
        })

    with get_session() as s:
        personajes_repo.reemplazar_todos(s, proyecto_id, filas)
        s.commit()

    if not filas:
        return "Sin personajes recurrentes: las escenas irán sin reparto fijo"
    nombres = ", ".join(
        f["clave"] + (" (objeto)" if f["tipo"] == "objeto" else "") for f in filas
    )
    return f"{len(filas)} personajes fijados ({nombres})"
