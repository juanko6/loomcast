"""Galería de imágenes independiente del pipeline de video.

Tres etapas, cada una disparada por el usuario desde la UI:
  1. mejorar_prompt  — el LLM convierte la idea/petición en un prompt en inglés.
  2. generar_previews — 4 imágenes a resolución nativa con distinta seed.
  3. generar_final    — ESRGAN x4 sobre la preview elegida (máxima resolución).

El modo (`tipo`) decide la etapa 1 (qué prompt de sistema) y la etapa 2 (generar
desde texto o editar la imagen subida); el `motor` guardado en la entrada decide
con qué modelo de [imagen.motores] se hace esa etapa 2.
"""
import random

from ...clients import comfy, llm
from ...config import GALERIA_DIR, PROMPTS_DIR
from ...db import get_session
from ...repositories import galeria as galeria_repo
from ...schemas import ImagenLibrePromptLLM
from .. import progreso

N_PREVIEWS = 4


def carpeta(imagen_id: int):
    return GALERIA_DIR / str(imagen_id)


def ruta_fuente(imagen_id: int):
    return carpeta(imagen_id) / "fuente.png"


def ruta_preview(imagen_id: int, indice: int):
    return carpeta(imagen_id) / f"preview_{indice}.png"


def ruta_final(imagen_id: int):
    return carpeta(imagen_id) / "final.png"


def _sistema(tipo: str) -> str:
    nombre = "imagen_editar.md" if tipo == "editar" else "imagen_generar.md"
    return (PROMPTS_DIR / nombre).read_text()


def mejorar_prompt(imagen_id: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")
        tipo, idea = img.tipo, img.idea

    if tipo == "editar" and not ruta_fuente(imagen_id).exists():
        raise ValueError("No hay imagen de origen; súbela antes de mejorar el prompt")

    r = llm.chat(_sistema(tipo), idea, ImagenLibrePromptLLM)

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.guardar_prompt(s, img, r.prompt)
        s.commit()
    return "Prompt mejorado"


def generar_previews(imagen_id: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")
        if not img.prompt:
            raise ValueError("La imagen no tiene prompt todavía")
        tipo, prompt, width, height = img.tipo, img.prompt, img.width, img.height
        motor = img.motor or None

    carpeta(imagen_id).mkdir(parents=True, exist_ok=True)
    seeds = [random.randint(0, 2**31 - 1) for _ in range(N_PREVIEWS)]
    try:
        for i, seed in enumerate(seeds):
            progreso.lote(i, N_PREVIEWS, "preview")
            destino = ruta_preview(imagen_id, i)
            if tipo == "editar":
                comfy.editar_imagen(
                    ruta_fuente(imagen_id), prompt, seed, destino, motor
                )
            else:
                comfy.generar_imagen(prompt, seed, destino, width, height, motor)
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.guardar_previews(s, img, seeds)
        s.commit()
    return f"{N_PREVIEWS} previews generadas"


def generar_final(imagen_id: int, indice: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")

    origen = ruta_preview(imagen_id, indice)
    if not origen.exists():
        raise ValueError(f"No existe la preview {indice}")

    try:
        comfy.upscale_imagen(origen, ruta_final(imagen_id))
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.set_seed_elegido(s, img, indice)
        s.commit()
    return f"Imagen final ampliada (preview {indice + 1})"
