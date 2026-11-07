from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..schemas import (
    GaleriaAnimadaIn,
    GaleriaEscalarIn,
    GaleriaFinalIn,
    GaleriaGenerarIn,
    GaleriaMovimientoIn,
    GaleriaPreviewsIn,
    GaleriaPromptIn,
)
from ..services import galeria as galeria_service
from ..services.pipeline import imagen_animada, imagen_libre

router = APIRouter(prefix="/api/galeria", tags=["galeria"])


@router.get("")
def listar():
    return galeria_service.listar()


@router.get("/motores")
def motores(modo: str | None = None):
    """Motores de imagen disponibles, opcionalmente filtrados por modo
    (generar | editar). Alimenta el selector de modelo de la UI."""
    return galeria_service.motores(modo)


@router.post("")
def crear_generar(body: GaleriaGenerarIn):
    if not body.idea.strip():
        raise HTTPException(400, "La idea no puede estar vacía")
    try:
        return galeria_service.crear_generar(
            body.idea, body.width, body.height, body.motor
        )
    except galeria_service.MotorInvalido as e:
        raise HTTPException(400, str(e))


@router.post("/animada")
def crear_animada(body: GaleriaAnimadaIn):
    if not body.idea.strip():
        raise HTTPException(400, "Describe la imagen que quieres animar")
    return galeria_service.crear_animada(body.idea, body.width, body.height)


@router.post("/editar")
async def crear_editar(
    idea: str = Form(...),
    imagen: UploadFile = File(...),
    width: int = Form(768),
    height: int = Form(1344),
    motor: str | None = Form(None),
):
    if not idea.strip():
        raise HTTPException(400, "Describe los cambios que quieres aplicar")
    data = await imagen.read()
    try:
        return galeria_service.crear_editar(idea, width, height, data, motor)
    except galeria_service.MotorInvalido as e:
        raise HTTPException(400, str(e))
    except OSError as e:
        raise HTTPException(400, f"No se pudo leer la imagen: {e}")


@router.post("/quitarfondo")
async def crear_quitarfondo(imagen: UploadFile = File(...)):
    data = await imagen.read()
    try:
        return galeria_service.crear_quitarfondo(imagen.filename or "", data)
    except OSError as e:
        raise HTTPException(400, f"No se pudo leer la imagen: {e}")


@router.get("/{imagen_id}")
def detalle(imagen_id: int):
    try:
        return galeria_service.detalle(imagen_id)
    except galeria_service.ImagenNoExiste:
        raise HTTPException(404, "Imagen no existe")


@router.post("/{imagen_id}/mejorar")
def mejorar(imagen_id: int):
    try:
        return {"job_id": galeria_service.lanzar_mejorar(imagen_id)}
    except galeria_service.ImagenNoExiste:
        raise HTTPException(404, "Imagen no existe")


@router.put("/{imagen_id}/prompt")
def editar_prompt(imagen_id: int, body: GaleriaPromptIn):
    try:
        galeria_service.editar_prompt(imagen_id, body.prompt)
        return {"ok": True}
    except galeria_service.ImagenNoExiste:
        raise HTTPException(404, "Imagen no existe")


@router.post("/{imagen_id}/previews")
def previews(imagen_id: int, body: GaleriaPreviewsIn | None = None):
    b = body or GaleriaPreviewsIn()
    try:
        return {"job_id": galeria_service.lanzar_previews(imagen_id, b.width, b.height)}
    except galeria_service.ImagenNoExiste:
        raise HTTPException(404, "Imagen no existe")


@router.post("/{imagen_id}/final")
def final(imagen_id: int, body: GaleriaFinalIn):
    try:
        return {"job_id": galeria_service.lanzar_final(imagen_id, body.indice)}
    except galeria_service.ImagenNoExiste:
        raise HTTPException(404, "Imagen no existe")
    except galeria_service.PasoInvalido as e:
        raise HTTPException(400, str(e))


def _paso(fn, *args):
    """Lanza una operación de la animada traduciendo sus errores a HTTP."""
    try:
        return fn(*args)
    except galeria_service.ImagenNoExiste:
        raise HTTPException(404, "Imagen no existe")
    except galeria_service.PasoInvalido as e:
        raise HTTPException(409, str(e))


@router.put("/{imagen_id}/movimiento")
def guardar_movimiento(imagen_id: int, body: GaleriaMovimientoIn):
    if not body.prompt.strip():
        raise HTTPException(400, "Describe qué quieres que se mueva")
    _paso(galeria_service.guardar_movimiento, imagen_id, body.prompt, body.duracion_s)
    return {"ok": True}


@router.post("/{imagen_id}/movimiento/mejorar")
def mejorar_movimiento(imagen_id: int):
    return {"job_id": _paso(galeria_service.lanzar_mejorar_movimiento, imagen_id)}


@router.post("/{imagen_id}/animar")
def animar(imagen_id: int):
    return {"job_id": _paso(galeria_service.lanzar_animar, imagen_id)}


@router.post("/{imagen_id}/escalar")
def escalar(imagen_id: int, body: GaleriaEscalarIn):
    return {"job_id": _paso(galeria_service.lanzar_escalar, imagen_id, body.escala)}


@router.delete("/{imagen_id}")
def borrar(imagen_id: int):
    try:
        return galeria_service.borrar(imagen_id)
    except galeria_service.ImagenNoExiste:
        raise HTTPException(404, "Imagen no existe")


def _archivo(ruta, detalle: str):
    if not ruta.exists():
        raise HTTPException(404, detalle)
    return FileResponse(ruta, media_type="image/png")


@router.get("/{imagen_id}/fuente")
def fuente(imagen_id: int):
    return _archivo(imagen_libre.ruta_fuente(imagen_id), "Sin imagen de origen")


@router.get("/{imagen_id}/preview/{indice}")
def preview(imagen_id: int, indice: int):
    return _archivo(imagen_libre.ruta_preview(imagen_id, indice), "Preview no generada")


@router.get("/{imagen_id}/final")
def imagen_final(imagen_id: int):
    return _archivo(imagen_libre.ruta_final(imagen_id), "Aún no hay imagen final")


@router.get("/{imagen_id}/video")
def video(imagen_id: int, escala: str | None = None):
    """El bucle animado; con `escala` (1080p | 2k | 4k), su versión escalada."""
    if escala is not None and escala not in imagen_animada.LADO_ESCALA:
        raise HTTPException(400, "Escala desconocida: usa 1080p, 2k o 4k")
    ruta = imagen_animada.ruta_video(imagen_id, escala)
    if not ruta.exists():
        raise HTTPException(404, "Aún no hay vídeo")
    return FileResponse(ruta, media_type="video/mp4")
