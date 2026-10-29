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

from ... import parada
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
from ...repositories import reparto as reparto_repo
from .. import progreso

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
    datos = _preparar(proyecto_id, clave, nuevo_seed)
    try:
        return _pintar(clave, *datos)
    finally:
        comfy.liberar_memoria()


def pendientes(s, proyecto_id: int) -> list[str]:
    """Claves del reparto a las que les falta su retrato.

    Sin ficha no se retrata a nadie (no hay nada que dibujar), así que esos no
    cuentan como pendientes: si contaran, el autopiloto pediría una y otra vez
    una etapa que no puede avanzar.
    """
    p = proyectos_repo.obtener(s, proyecto_id)
    if p is None:
        return []
    return [
        x.clave
        for x in personajes_repo.por_proyecto(s, proyecto_id)
        if (x.ficha or "").strip() and not ruta_retrato(p.slug, x.clave).exists()
    ]


def generar_retratos(proyecto_id: int) -> str:
    """Retrata de una tirada a todo el reparto que no tenga cara.

    A mano los retratos se piden uno a uno, porque uno mira la cara que salió y
    decide si la rehace. En automático eso serían N clics, así que esta etapa
    hace el lote entero: mira la bandera de parada entre personaje y personaje
    (un retrato no se escribe hasta que ComfyUI lo entrega, así que cortar aquí
    no deja PNG a medias) y suelta la memoria **una vez al final** y no tras
    cada cara, que es lo que haría descargar y recargar ~19 GB por personaje.

    Los que ya tienen retrato no se tocan: rehacer una cara es una decisión, y
    la de este reparto puede venir del reparto propio o de una serie.
    """
    with get_session() as s:
        if proyectos_repo.obtener(s, proyecto_id) is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        claves = pendientes(s, proyecto_id)

    if not claves:
        return "Nadie del reparto necesita retrato"

    hechos = []
    try:
        for i, clave in enumerate(claves):
            parada.comprobar(f"quedaban {len(claves) - i} retratos")
            progreso.lote(i, len(claves), "retrato")
            _pintar(clave, *_preparar(proyecto_id, clave, nuevo_seed=False))
            hechos.append(clave)
    finally:
        comfy.liberar_memoria()
    return f"{len(hechos)} retratos generados ({', '.join(hechos)})"


def _preparar(proyecto_id: int, clave: str,
              nuevo_seed: bool = False) -> tuple[str, int, str, str]:
    """Valida y devuelve (prompt, seed, slug, tipo).

    Va aparte de pintar porque no toca ComfyUI: un personaje que no existe o sin
    ficha tiene que fallar **antes** de que haya nada cargado, y entonces
    tampoco hay memoria que soltar.
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

    return _prompt(ficha, tipo), seed, slug, tipo


def _prompt(ficha: str, tipo: str) -> str:
    """La ficha más el encuadre que le toca a su tipo."""
    encuadre = ENCUADRE_OBJETO if tipo == "objeto" else ENCUADRE_PERSONA
    return f"{ficha}, {encuadre}"


def _imagen(prompt: str, seed: int, destino) -> None:
    """La llamada a ComfyUI, con los ajustes de [personajes] de config.toml.

    Lo único que cambia entre el retrato de un personaje de proyecto y el de un
    miembro del reparto propio es dónde se escribe el PNG: el encuadre, el
    motor y el tamaño son los mismos, y deben serlo, porque las dos imágenes
    hacen el mismo trabajo (ser la referencia visual de esa persona).
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    comfy.generar_imagen(
        prompt, seed, destino,
        PERSONAJE_WIDTH, PERSONAJE_HEIGHT, PERSONAJE_MOTOR,
    )


def _pintar(clave: str, prompt: str, seed: int, slug: str, tipo: str) -> str:
    """Una cara. Sin soltar la memoria: lo hace quien llama, porque el lote la
    suelta una sola vez al final y no tras cada personaje."""
    _imagen(prompt, seed, ruta_retrato(slug, clave))
    como = " como objeto" if tipo == "objeto" else ""
    return f"Retrato de {clave} generado{como} (seed {seed})"


def generar_retrato_reparto(miembro_id: int, nuevo_seed: bool = False) -> str:
    """La cara de alguien del reparto propio, sin pasar por ningún proyecto.

    Hasta las series, la cara del reparto siempre venía copiada del proyecto
    donde se promovió a esa persona, y eso bastaba: la descubrías escribiendo un
    vídeo. Una serie empieza al revés —el hilo dice quiénes son antes del primer
    capítulo— y entonces hace falta poder retratarlos ahí mismo, para que el
    episodio 1 ya se traiga la cara buena en vez de inventarse una.

    Es el mismo encuadre y el mismo motor que el retrato de un personaje de
    proyecto: lo que cambia es dónde se guarda. Y el seed se guarda en el
    miembro, así que rehacerle la cara en un proyecto "con el mismo seed" sigue
    dando esta misma persona.
    """
    with get_session() as s:
        m = reparto_repo.obtener(s, miembro_id)
        if m is None:
            raise ValueError(f"El miembro {miembro_id} no está en el reparto")
        if not (m.ficha or "").strip():
            raise ValueError(
                f"«{m.nombre}» no tiene ficha; sin descripción física no hay "
                "nada que retratar."
            )
        if nuevo_seed or not m.seed:
            m.seed = random.randint(0, 2**31 - 1)
            s.commit()
        prompt = _prompt(m.ficha, m.tipo or "persona")
        seed, slug, nombre = m.seed, m.slug, m.nombre

    try:
        _imagen(prompt, seed, reparto_repo.ruta_retrato(slug))
    finally:
        comfy.liberar_memoria()
    return f"Retrato de «{nombre}» generado para el reparto (seed {seed})"
