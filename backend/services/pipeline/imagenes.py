"""Etapa 7 — IMAGENES: una imagen 9:16 por escena, vía ComfyUI.

Cada escena va por uno de dos caminos:

  - sin personajes (o sin retrato hecho) → texto→imagen con el motor de siempre;
  - con personajes retratados → se generan **a partir de sus retratos**, que es
    lo único que mantiene la misma cara de una escena a otra. Cuesta más o menos
    lo mismo y es la razón de ser del reparto.

Al terminar el lote se descargan los modelos de ComfyUI (POST /free) para
devolver la memoria unificada al resto del pipeline.
"""
import random
import time
from pathlib import Path

from ...clients import comfy
from ...config import (
    IMAGEN_HEIGHT,
    IMAGEN_WIDTH,
    PERSONAJE_MOTOR_ESCENA,
    PROYECTOS_DIR,
)
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import personajes as personajes_repo
from ...repositories import proyectos as proyectos_repo
from .. import progreso
from .retratos import ruta_retrato

# Lo que se le antepone al prompt de la escena cuando entra por referencias. El
# nodo numera las imágenes como "Picture 1", "Picture 2"…, así que se le puede
# hablar de ellas; lo que hay que dejar claro es que la cara y la ropa vienen de
# ahí y no de lo que diga el texto.
PREFIJO_REFERENCIA = (
    "The people shown in the reference pictures appear in this scene. Keep each "
    "person's face, hair and clothing exactly as in their picture. Scene: "
)


def ruta_imagen(slug: str, orden: int):
    return PROYECTOS_DIR / slug / "imagenes" / f"{orden:02d}.png"


def _retratos_de(escena_personajes: str, slug: str) -> list[Path]:
    """Retratos disponibles de los personajes de una escena.

    Se recorta a las referencias que admita el motor de escena: con dos
    personajes y un motor de una sola, entrar con el primero da mejor resultado
    que caer a texto y perder las dos caras. El tope se pregunta aquí, y no lo
    pasa quien llama, para que no pueda descuadrarse con el motor que se acaba
    usando.
    """
    claves = [c for c in (escena_personajes or "").split(",") if c]
    if not claves:
        return []
    tope = comfy.referencias_admitidas(PERSONAJE_MOTOR_ESCENA)
    existentes = [ruta_retrato(slug, c) for c in claves]
    return [r for r in existentes if r.exists()][:tope]


def _generar_una(escena: dict, slug: str, refs: list[Path]) -> bool:
    """Genera la imagen de una escena. Devuelve si usó retratos.

    `refs` viene resuelto de fuera porque el orden de generación depende de si
    los hay: ver `generar_imagenes`.
    """
    destino = ruta_imagen(slug, escena["orden"])
    if refs:
        comfy.editar_imagen(
            refs,
            PREFIJO_REFERENCIA + escena["prompt"],
            escena["seed"],
            destino,
            PERSONAJE_MOTOR_ESCENA,
            IMAGEN_WIDTH,
            IMAGEN_HEIGHT,
        )
        return True
    comfy.generar_imagen(escena["prompt"], escena["seed"], destino)
    return False


def generar_imagenes(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            {"orden": e.orden, "prompt": e.prompt, "seed": e.seed,
             "personajes": e.personajes}
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]
        slug = p.slug

    if not escenas:
        raise ValueError("El proyecto no tiene escenas; genera las escenas primero")

    (PROYECTOS_DIR / slug / "imagenes").mkdir(parents=True, exist_ok=True)

    # Las escenas con reparto van por el motor de edición y las demás por el de
    # texto→imagen, así que generarlas en el orden del guion hace que ComfyUI
    # suelte un stack y cargue el otro en cada cambio: con doce escenas
    # alternadas eso fueron siete cargas, ~19 GB cada vez que toca el de
    # personajes, y los picos acaban en swap. Agrupadas son dos cargas.
    # El sort es estable, así que dentro de cada grupo se respeta el guion, y
    # cada imagen se guarda en su `orden`: el resultado es el mismo.
    trabajos = [(e, _retratos_de(e["personajes"], slug)) for e in escenas]
    trabajos.sort(key=lambda par: bool(par[1]))

    con_retrato = 0
    try:
        for i, (e, refs) in enumerate(trabajos):
            progreso.lote(i, len(trabajos), "imagen")
            t0 = time.time()
            con_retrato += _generar_una(e, slug, refs)
            _anotar_tiempo(proyecto_id, e["orden"], time.time() - t0)
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "IMAGENES")
        s.commit()
    if not con_retrato:
        return f"{len(escenas)} imágenes generadas"
    return (
        f"{len(escenas)} imágenes generadas, {con_retrato} con el reparto "
        f"({len(escenas) - con_retrato} sin personajes)"
    )


def _anotar_tiempo(proyecto_id: int, orden: int, segundos: float) -> None:
    with get_session() as s:
        for e in escenas_repo.por_proyecto(s, proyecto_id):
            if e.orden == orden:
                e.imagen_s = round(segundos, 1)
        s.commit()


def regenerar_imagen(proyecto_id: int, orden: int, nuevo_seed: bool = True) -> str:
    """Regenera la imagen de una sola escena.

    Con `nuevo_seed` sale una imagen distinta (lo normal cuando la actual no
    convence); sin él se reusa el seed guardado, de modo que la imagen solo
    cambia si se editó el prompt.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escena = next(
            (e for e in escenas_repo.por_proyecto(s, proyecto_id) if e.orden == orden),
            None,
        )
        if escena is None:
            raise ValueError(f"El proyecto no tiene escena {orden}")
        if nuevo_seed:
            escena.seed = random.randint(0, 2**31 - 1)
            s.commit()
        datos = {"orden": orden, "prompt": escena.prompt, "seed": escena.seed,
                 "personajes": escena.personajes}
        slug, seed = p.slug, escena.seed

    (PROYECTOS_DIR / slug / "imagenes").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        con_retrato = _generar_una(datos, slug, _retratos_de(datos["personajes"], slug))
    finally:
        comfy.liberar_memoria()
    tardo = time.time() - t0
    _anotar_tiempo(proyecto_id, orden, tardo)
    con_que = " con el reparto" if con_retrato else ""
    return (
        f"Imagen de la escena {orden + 1} regenerada{con_que} en {tardo:.0f}s "
        f"(seed {seed})"
    )
