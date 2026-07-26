"""Galería — Quitar fondo: deja el sujeto de una imagen subida sobre fondo
transparente (PNG RGBA). Un solo paso, sin LLM ni previews."""
from ...clients import fondo
from ...db import get_session
from ...repositories import galeria as galeria_repo
from .imagen_libre import ruta_final, ruta_fuente


def quitar_fondo(imagen_id: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")

    origen = ruta_fuente(imagen_id)
    if not origen.exists():
        raise ValueError("No hay imagen de origen")

    fondo.quitar_fondo(origen, ruta_final(imagen_id))

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.set_estado(s, img, "final")
        s.commit()
    return "Fondo eliminado"
