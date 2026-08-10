"""Etapa 7 — IMAGENES: una imagen 9:16 por escena con Z-Image vía ComfyUI.

Al terminar el lote se descargan los modelos de ComfyUI (POST /free) para
devolver la memoria unificada al resto del pipeline.
"""
import random
import time

from ...clients import comfy
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo
from .. import progreso


def ruta_imagen(slug: str, orden: int):
    return PROYECTOS_DIR / slug / "imagenes" / f"{orden:02d}.png"


def generar_imagenes(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            {"orden": e.orden, "prompt": e.prompt, "seed": e.seed}
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]
        slug = p.slug

    if not escenas:
        raise ValueError("El proyecto no tiene escenas; genera las escenas primero")

    (PROYECTOS_DIR / slug / "imagenes").mkdir(parents=True, exist_ok=True)
    try:
        for i, e in enumerate(escenas):
            progreso.lote(i, len(escenas), "imagen")
            t0 = time.time()
            comfy.generar_imagen(e["prompt"], e["seed"], ruta_imagen(slug, e["orden"]))
            _anotar_tiempo(proyecto_id, e["orden"], time.time() - t0)
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "IMAGENES")
        s.commit()
    return f"{len(escenas)} imágenes generadas"


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
        prompt, seed, slug = escena.prompt, escena.seed, p.slug

    (PROYECTOS_DIR / slug / "imagenes").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        comfy.generar_imagen(prompt, seed, ruta_imagen(slug, orden))
    finally:
        comfy.liberar_memoria()
    tardo = time.time() - t0
    _anotar_tiempo(proyecto_id, orden, tardo)
    return f"Imagen de la escena {orden + 1} regenerada en {tardo:.0f}s (seed {seed})"
