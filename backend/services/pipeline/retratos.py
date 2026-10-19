"""Retrato de referencia de un personaje: su cara oficial.

La ficha del reparto (ver casting.py) fija ropa, pelo, edad y complexión
repitiendo las mismas palabras en cada escena, pero no la cara: con solo texto
el generador dibuja una persona nueva cada vez. El retrato es la imagen que
luego se le pasa como referencia visual al generar sus escenas, que es lo único
que sí fija los rasgos.

Se genera una vez por personaje y se reutiliza en todas sus escenas, así que
aquí compensa el motor que mejor cara dé y no el más rápido: ver [personajes]
en config.toml.
"""
import random

from ...clients import comfy
from ...config import (
    PERSONAJE_HEIGHT,
    PERSONAJE_MOTOR,
    PERSONAJE_WIDTH,
    PROYECTOS_DIR,
)
from ...db import get_session
from ...repositories import personajes as personajes_repo
from ...repositories import proyectos as proyectos_repo

# Encuadre del retrato. Deliberadamente neutro y bien iluminado: esto no es una
# escena, es una ficha policial. Cuanto más limpia y frontal sea la referencia,
# mejor la extrae el motor de edición al montarla en las escenas. Por eso
# tampoco se le mete el estilo visual de la plantilla, que en drama pide luz
# dura y sombras y taparía justo lo que hay que ver.
ENCUADRE_PERSONA = (
    "character reference portrait, waist-up shot, facing the camera, neutral "
    "expression, plain neutral grey seamless background, soft even diffused "
    "lighting, no harsh shadows, sharp focus on the face, entire head visible, "
    "photorealistic, natural skin texture"
)

# El reparto admite objetos a propósito (un barco, un mapa, una máquina que
# vuelve en varias escenas tampoco debe mutar), y ahí el encuadre de persona
# hacía daño: pedía cara, cabeza y piel, así que el generador se las inventaba
# encima del objeto aunque la ficha dijera "no humans are visible" — cinco
# términos pidiendo rostro le ganan a una negación. Este encuadre pide lo mismo
# que el otro (sujeto centrado, fondo liso, luz pareja) sin nombrar nada humano,
# y lo niega explícitamente al final.
ENCUADRE_OBJETO = (
    "object reference photograph, the whole object centred and fully visible, "
    "three-quarter view, plain neutral grey seamless background, soft even "
    "diffused lighting, no harsh shadows, sharp focus, photorealistic, visible "
    "material texture and wear, no people, no person, no face, no hands"
)


def carpeta(slug: str):
    return PROYECTOS_DIR / slug / "personajes"


def ruta_retrato(slug: str, clave: str):
    return carpeta(slug) / f"{clave}.png"


def generar_retrato(proyecto_id: int, clave: str, nuevo_seed: bool = False) -> str:
    """Genera (o rehace) el retrato de un personaje del reparto.

    Con `nuevo_seed` sale otra cara distinta, que es lo normal cuando la actual
    no convence; sin él se reusa el seed guardado y la imagen solo cambia si se
    editó la ficha.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        personaje = next(
            (x for x in personajes_repo.por_proyecto(s, proyecto_id) if x.clave == clave),
            None,
        )
        if personaje is None:
            raise ValueError(f"El proyecto no tiene ningún personaje '{clave}'")
        if not personaje.ficha.strip():
            raise ValueError(
                f"El personaje '{clave}' no tiene ficha; sin descripción física "
                "no hay nada que retratar."
            )
        if nuevo_seed or not personaje.seed:
            personaje.seed = random.randint(0, 2**31 - 1)
            s.commit()
        ficha, seed, slug = personaje.ficha, personaje.seed, p.slug
        tipo = personaje.tipo or "persona"

    encuadre = ENCUADRE_OBJETO if tipo == "objeto" else ENCUADRE_PERSONA
    prompt = f"{ficha}, {encuadre}"
    carpeta(slug).mkdir(parents=True, exist_ok=True)
    try:
        comfy.generar_imagen(
            prompt,
            seed,
            ruta_retrato(slug, clave),
            PERSONAJE_WIDTH,
            PERSONAJE_HEIGHT,
            PERSONAJE_MOTOR,
        )
    finally:
        comfy.liberar_memoria()
    como = " como objeto" if tipo == "objeto" else ""
    return f"Retrato de {clave} generado{como} (seed {seed})"
