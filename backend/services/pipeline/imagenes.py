"""Etapa 7 — IMAGENES: una imagen 9:16 por escena con Z-Image vía ComfyUI.

Al terminar el lote se descargan los modelos de ComfyUI (POST /free) para
devolver la memoria unificada al resto del pipeline.
"""
from ...clients import comfy
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo


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
        for e in escenas:
            comfy.generar_imagen(e["prompt"], e["seed"], ruta_imagen(slug, e["orden"]))
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "IMAGENES")
        s.commit()
    return f"{len(escenas)} imágenes generadas"
