from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import RepartoDesdeProyectoIn, RepartoTraerIn
from ..services import reparto as reparto_service

router = APIRouter(prefix="/api/reparto", tags=["reparto"])

# Las rutas van todas aquí, incluida la de traer a alguien a un proyecto, aunque
# esa escriba en el proyecto: la feature se entiende de un tirón si el reparto
# propio tiene un solo router, y el banco de voces solo partió sus rutas porque
# elegir voz es un campo del proyecto, no un alta.


@router.get("")
def listar():
    return reparto_service.listar()


@router.post("")
def promover(body: RepartoDesdeProyectoIn):
    """Guarda en el reparto propio a un personaje que ya quedó bien en un vídeo."""
    try:
        return reparto_service.promover(body.proyecto_id, body.clave, body.nombre)
    except reparto_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except reparto_service.PersonajeNoExiste:
        raise HTTPException(404, "El proyecto no tiene ese personaje")
    except reparto_service.SinFicha:
        raise HTTPException(
            400, "Ese personaje no tiene ficha; sin descripción física no hay "
                 "nada que guardar."
        )
    except reparto_service.SlugOcupado as e:
        raise HTTPException(409, f"Ya hay alguien en el reparto con ese nombre: {e}")


@router.put("/{slug}")
def actualizar(slug: str, body: RepartoDesdeProyectoIn):
    """Pisa al miembro con la versión de un proyecto (ficha, tipo, seed, cara)."""
    try:
        return reparto_service.actualizar(slug, body.proyecto_id, body.clave)
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto")
    except reparto_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except reparto_service.PersonajeNoExiste:
        raise HTTPException(404, "El proyecto no tiene ese personaje")
    except reparto_service.SinFicha:
        raise HTTPException(400, "Ese personaje no tiene ficha")


@router.post("/{slug}/traer")
def traer(slug: str, body: RepartoTraerIn):
    try:
        return reparto_service.traer(slug, body.proyecto_id)
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto")
    except reparto_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.delete("/{slug}")
def borrar(slug: str):
    try:
        return reparto_service.borrar(slug)
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto")


@router.get("/{slug}/retrato")
def retrato(slug: str):
    try:
        return FileResponse(reparto_service.ruta_retrato(slug), media_type="image/png")
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Retrato no disponible")
