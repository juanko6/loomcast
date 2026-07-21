"""Etapa 8 — UPSCALE: Real-ESRGAN x4 sobre cada imagen de escena.

Reescalar la imagen (no el video) es lo eficiente: 12 imágenes vs miles de
cuadros. La imagen ampliada (3072x5376) da margen de nitidez para el zoom/
paneo del Ken Burns, que luego produce el clip a 1080x1920.
"""
from ...clients import comfy
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo


def generar_upscale(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        ordenes = [e.orden for e in escenas_repo.por_proyecto(s, proyecto_id)]
        slug = p.slug

    if not ordenes:
        raise ValueError("El proyecto no tiene escenas")

    base = PROYECTOS_DIR / slug
    origen_dir = base / "imagenes"
    destino_dir = base / "upscale"
    destino_dir.mkdir(parents=True, exist_ok=True)

    faltantes = [o for o in ordenes if not (origen_dir / f"{o:02d}.png").exists()]
    if faltantes:
        raise ValueError(f"Faltan imágenes de las escenas {faltantes}")

    try:
        for o in ordenes:
            comfy.upscale_imagen(
                origen_dir / f"{o:02d}.png", destino_dir / f"{o:02d}.png"
            )
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "UPSCALE")
        s.commit()
    return f"{len(ordenes)} imágenes reescaladas con ESRGAN x4"
