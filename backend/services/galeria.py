"""Lógica de la galería de imágenes (crear, subir origen, detalle, borrar).

Las etapas pesadas (mejorar prompt, previews, final) viven en
`pipeline/imagen_libre.py` y se disparan por la cola de jobs; aquí queda lo que
atiende directamente a la API HTTP.
"""
import io
import json
import shutil

from PIL import Image

from ..db import get_session
from ..repositories import galeria as galeria_repo
from ..repositories import jobs as jobs_repo
from ..services.pipeline import imagen_libre
from ..workers import queue

TIPOS_JOB = [
    "mejorar_prompt_imagen",
    "generar_previews_imagen",
    "generar_final_imagen",
    "quitar_fondo",
]
# Tamaño mínimo/máximo del lado en píxeles (múltiplos de 64 fuera).
LADO_MIN, LADO_MAX = 256, 1536


class ImagenNoExiste(LookupError):
    pass


def _normalizar_lado(v: int) -> int:
    v = max(LADO_MIN, min(LADO_MAX, int(v)))
    return round(v / 64) * 64


def crear_generar(idea: str, width: int, height: int) -> dict:
    w, h = _normalizar_lado(width), _normalizar_lado(height)
    with get_session() as s:
        img = galeria_repo.crear(s, "generar", idea.strip(), w, h)
        s.commit()
        imagen_id = img.id
    # Mejorar el prompt con el LLM es un paso opcional: lo lanza el usuario
    # desde la UI (`lanzar_mejorar`), no se encola al crear.
    return {"id": imagen_id}


def crear_editar(idea: str, width: int, height: int, data: bytes) -> dict:
    w, h = _normalizar_lado(width), _normalizar_lado(height)
    with get_session() as s:
        img = galeria_repo.crear(s, "editar", idea.strip(), w, h)
        s.commit()
        imagen_id = img.id

    # Normaliza cualquier formato de entrada (PNG/JPG/WEBP…) a un PNG RGB, para
    # que la subida a ComfyUI, la edición y ESRGAN trabajen consistentes.
    imagen_libre.carpeta(imagen_id).mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(data)).convert("RGB").save(
        imagen_libre.ruta_fuente(imagen_id), "PNG"
    )
    return {"id": imagen_id}


def lanzar_mejorar(imagen_id: int) -> int:
    """Mejora el prompt con el LLM. Paso opcional, a petición del usuario."""
    with get_session() as s:
        if galeria_repo.obtener(s, imagen_id) is None:
            raise ImagenNoExiste(imagen_id)
    return queue.encolar("mejorar_prompt_imagen", imagen_id)


def crear_quitarfondo(nombre: str, data: bytes) -> dict:
    """Sube una imagen y encola el quitado de fondo (sin LLM ni previews)."""
    with get_session() as s:
        img = galeria_repo.crear(s, "quitarfondo", (nombre or "imagen").strip(), 0, 0)
        s.commit()
        imagen_id = img.id

    imagen_libre.carpeta(imagen_id).mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(data)).convert("RGB").save(
        imagen_libre.ruta_fuente(imagen_id), "PNG"
    )
    job_id = queue.encolar("quitar_fondo", imagen_id)
    return {"id": imagen_id, "job_id": job_id}


def _ocupado(s, imagen_id: int) -> bool:
    return any(
        j.ref_id == imagen_id and j.tipo in TIPOS_JOB
        for j in jobs_repo.activos(s)
    )


def _a_dict(s, img) -> dict:
    return {
        "id": img.id,
        "tipo": img.tipo,
        "idea": img.idea,
        "prompt": img.prompt,
        "width": img.width,
        "height": img.height,
        "estado": img.estado,
        "seeds": json.loads(img.seeds or "[]"),
        "seed_elegido": img.seed_elegido,
        "ocupado": _ocupado(s, img.id),
    }


def listar() -> list[dict]:
    with get_session() as s:
        return [
            {
                "id": img.id,
                "tipo": img.tipo,
                "idea": img.idea,
                "estado": img.estado,
            }
            for img in galeria_repo.listar(s)
        ]


def detalle(imagen_id: int) -> dict:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ImagenNoExiste(imagen_id)
        return _a_dict(s, img)


def editar_prompt(imagen_id: int, prompt: str) -> None:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ImagenNoExiste(imagen_id)
        img.prompt = prompt
        s.commit()


def lanzar_previews(imagen_id: int, width: int | None, height: int | None) -> int:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ImagenNoExiste(imagen_id)
        if width is not None and height is not None:
            galeria_repo.guardar_tamano(
                s, img, _normalizar_lado(width), _normalizar_lado(height)
            )
            s.commit()
    return queue.encolar("generar_previews_imagen", imagen_id)


def lanzar_final(imagen_id: int, indice: int) -> int:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ImagenNoExiste(imagen_id)
    return queue.encolar("generar_final_imagen", imagen_id, indice=indice)


def borrar(imagen_id: int) -> dict:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ImagenNoExiste(imagen_id)
        galeria_repo.borrar(s, img)
        s.commit()
    carpeta = imagen_libre.carpeta(imagen_id)
    archivos = 0
    if carpeta.exists():
        archivos = sum(1 for _ in carpeta.rglob("*") if _.is_file())
        shutil.rmtree(carpeta)
    return {"borrada": imagen_id, "archivos": archivos}
