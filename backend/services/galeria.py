"""Lógica de la galería de imágenes (crear, subir origen, detalle, borrar).

Las etapas pesadas (mejorar prompt, previews, final) viven en
`pipeline/imagen_libre.py` y se disparan por la cola de jobs; aquí queda lo que
atiende directamente a la API HTTP.
"""
import io
import json
import shutil

from PIL import Image

from ..config import IMAGEN_MOTOR_EDITAR, IMAGEN_MOTOR_GENERAR, IMAGEN_MOTORES
from ..db import get_session
from ..repositories import galeria as galeria_repo
from ..repositories import jobs as jobs_repo
from ..services.pipeline import imagen_animada, imagen_libre
from ..workers import queue

TIPOS_JOB = [
    "mejorar_prompt_imagen",
    "generar_previews_imagen",
    "generar_final_imagen",
    "quitar_fondo",
    "mejorar_movimiento_animada",
    "animar_imagen",
    "escalar_animada",
]
# Estados de una animada que ya tiene una preview aprobada.
ESTADOS_APROBADA = ("final", "movimiento", "animada", "escalada")
# Tamaño mínimo/máximo del lado en píxeles (múltiplos de 64 fuera).
LADO_MIN, LADO_MAX = 256, 1536


class ImagenNoExiste(LookupError):
    pass


class MotorInvalido(ValueError):
    pass


class PasoInvalido(ValueError):
    """La entrada no está en el punto del flujo que pide la operación."""


def _normalizar_lado(v: int) -> int:
    v = max(LADO_MIN, min(LADO_MAX, int(v)))
    return round(v / 64) * 64


def _validar_motor(motor: str | None, modo: str) -> str:
    """Devuelve el motor a guardar: el pedido si sabe hacer `modo`, o el por
    defecto si no se pidió ninguno."""
    if not motor:
        return IMAGEN_MOTOR_GENERAR if modo == "generar" else IMAGEN_MOTOR_EDITAR
    m = IMAGEN_MOTORES.get(motor)
    if m is None or modo not in m.modos:
        raise MotorInvalido(
            f"'{motor}' no es un motor que sepa {modo} imágenes. Disponibles: "
            f"{[x.id for x in IMAGEN_MOTORES.values() if modo in x.modos]}"
        )
    return motor


def motores(modo: str | None = None) -> list[dict]:
    """Motores declarados, para que la UI pueble el selector.

    `defecto_en` lista los modos en los que ese motor va preseleccionado, que no
    tienen por qué ser todos los que sabe hacer.
    """
    defectos = {"generar": IMAGEN_MOTOR_GENERAR, "editar": IMAGEN_MOTOR_EDITAR}
    return [
        {
            "id": m.id,
            "nombre": m.nombre,
            "modos": m.modos,
            "defecto_en": [k for k, v in defectos.items() if v == m.id],
        }
        for m in IMAGEN_MOTORES.values()
        if modo is None or modo in m.modos
    ]


def crear_generar(idea: str, width: int, height: int, motor: str | None = None) -> dict:
    w, h = _normalizar_lado(width), _normalizar_lado(height)
    elegido = _validar_motor(motor, "generar")
    with get_session() as s:
        img = galeria_repo.crear(s, "generar", idea.strip(), w, h, elegido)
        s.commit()
        imagen_id = img.id
    # Mejorar el prompt con el LLM es un paso opcional: lo lanza el usuario
    # desde la UI (`lanzar_mejorar`), no se encola al crear.
    return {"id": imagen_id}


def crear_editar(
    idea: str, width: int, height: int, data: bytes, motor: str | None = None
) -> dict:
    w, h = _normalizar_lado(width), _normalizar_lado(height)
    elegido = _validar_motor(motor, "editar")
    with get_session() as s:
        img = galeria_repo.crear(s, "editar", idea.strip(), w, h, elegido)
        s.commit()
        imagen_id = img.id

    # Normaliza cualquier formato de entrada (PNG/JPG/WEBP…) a un PNG RGB, para
    # que la subida a ComfyUI, la edición y ESRGAN trabajen consistentes.
    imagen_libre.carpeta(imagen_id).mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(data)).convert("RGB").save(
        imagen_libre.ruta_fuente(imagen_id), "PNG"
    )
    return {"id": imagen_id}


def crear_animada(idea: str, width: int, height: int) -> dict:
    """Una imagen animada: arranca como una de generar (previews con el motor
    de generar por defecto, Z-Image) y sigue con el movimiento."""
    w, h = _normalizar_lado(width), _normalizar_lado(height)
    with get_session() as s:
        img = galeria_repo.crear(s, "animada", idea.strip(), w, h,
                                 _validar_motor(None, "generar"))
        s.commit()
        return {"id": img.id}


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
    motor = IMAGEN_MOTORES.get(img.motor)
    return {
        "id": img.id,
        "tipo": img.tipo,
        "motor": img.motor,
        "motor_nombre": motor.nombre if motor else img.motor,
        "idea": img.idea,
        "prompt": img.prompt,
        "width": img.width,
        "height": img.height,
        "estado": img.estado,
        "seeds": json.loads(img.seeds or "[]"),
        "seed_elegido": img.seed_elegido,
        "prompt_movimiento": img.prompt_movimiento or "",
        "duracion_s": img.duracion_s,
        "seed_video": img.seed_video,
        "escala": img.escala,
        # Qué vídeos hay en disco: "base" es el bucle tal cual sale de animar.
        "videos": [
            e for e in ("base", *imagen_animada.LADO_ESCALA)
            if imagen_animada.ruta_video(img.id, None if e == "base" else e).exists()
        ] if img.tipo == "animada" else [],
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


def lanzar_final(imagen_id: int, indice: int) -> int | None:
    """Aprueba una preview. En generar/editar eso es ampliarla con ESRGAN (un
    job); en una animada es solo quedársela, al momento, y devuelve None."""
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ImagenNoExiste(imagen_id)
        tipo = img.tipo
    if tipo == "animada":
        try:
            imagen_animada.aprobar(imagen_id, indice)
        except ValueError as e:
            raise PasoInvalido(str(e)) from e
        return None
    return queue.encolar("generar_final_imagen", imagen_id, indice=indice)


def _animada(s, imagen_id: int):
    img = galeria_repo.obtener(s, imagen_id)
    if img is None:
        raise ImagenNoExiste(imagen_id)
    if img.tipo != "animada":
        raise PasoInvalido("Solo una imagen animada tiene movimiento")
    if img.estado not in ESTADOS_APROBADA:
        raise PasoInvalido("Aprueba antes una de las previews")
    return img


def guardar_movimiento(imagen_id: int, prompt: str, duracion_s: int) -> None:
    with get_session() as s:
        img = _animada(s, imagen_id)
        estado = img.estado
        galeria_repo.guardar_movimiento(
            s, img, prompt.strip(), imagen_animada.acotar_duracion(duracion_s)
        )
        # Cambiar el texto no tira el vídeo que ya hay: sigue ahí hasta que se
        # vuelva a animar, y la entrada no debe aparentar que no lo tiene.
        if estado in ("animada", "escalada"):
            img.estado = estado
        s.commit()


def lanzar_mejorar_movimiento(imagen_id: int) -> int:
    with get_session() as s:
        img = _animada(s, imagen_id)
        if not img.prompt_movimiento.strip():
            raise PasoInvalido("Escribe primero qué quieres que se mueva")
    return queue.encolar("mejorar_movimiento_animada", imagen_id)


def lanzar_animar(imagen_id: int) -> int:
    with get_session() as s:
        img = _animada(s, imagen_id)
        if not img.prompt_movimiento.strip():
            raise PasoInvalido("Falta el prompt de movimiento")
    return queue.encolar("animar_imagen", imagen_id)


def lanzar_escalar(imagen_id: int, escala: str) -> int:
    with get_session() as s:
        _animada(s, imagen_id)
    if not imagen_animada.ruta_video(imagen_id).exists():
        raise PasoInvalido("Todavía no hay vídeo que escalar: anímalo primero")
    return queue.encolar("escalar_animada", imagen_id, escala=escala)


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
