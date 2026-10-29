from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import RepartoDesdeProyectoIn, RepartoTraerIn, VozSeleccionIn
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


@router.post("/{slug}/retrato")
def generar_retrato(slug: str, nuevo_seed: bool = False):
    """Le hace la cara aquí mismo, sin pasar por ningún proyecto.

    Es lo que una serie necesita: el hilo dice quiénes son antes del primer
    capítulo, y la cara hay que fijarla **antes** para que todos los episodios
    se traigan la misma. `nuevo_seed` da otra persona distinta, que es lo normal
    cuando la que salió no convence.
    """
    try:
        return reparto_service.encolar_retrato(slug, nuevo_seed)
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto")
    except reparto_service.SinFicha:
        raise HTTPException(400, "No tiene ficha: sin descripción física no hay "
                                 "nada que retratar.")


@router.post("/{slug}/voz")
def crear_su_voz(slug: str):
    """Le escribe una voz desde su ficha y la encola en el banco."""
    try:
        return reparto_service.crear_su_voz(slug)
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto")
    except reparto_service.SinFicha:
        raise HTTPException(400, "No tiene ficha: la voz se escribe desde ella.")


@router.put("/{slug}/voz")
def asignar_voz(slug: str, body: VozSeleccionIn):
    """Le pone una voz que ya está en el banco (cadena vacía se la quita)."""
    try:
        return reparto_service.asignar_voz(slug, body.voz)
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto")
    except reparto_service.VozNoExiste:
        raise HTTPException(404, "Esa voz no está en el banco")


@router.get("/{slug}/retrato")
def retrato(slug: str):
    try:
        return FileResponse(reparto_service.ruta_retrato(slug), media_type="image/png")
    except reparto_service.MiembroNoExiste:
        raise HTTPException(404, "Retrato no disponible")
