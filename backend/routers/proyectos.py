from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import GuionIn
from ..services import proyectos as proyectos_service

router = APIRouter(prefix="/api/proyectos", tags=["proyectos"])


@router.get("")
def listar():
    return proyectos_service.listar()


@router.get("/{pid}")
def detalle(pid: int):
    try:
        return proyectos_service.detalle(pid)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.put("/{pid}/guion")
def editar_guion(pid: int, body: GuionIn):
    try:
        return {"version": proyectos_service.editar_guion(pid, body.model_dump())}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.post("/{pid}/guion/regenerar")
def regenerar_guion(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_guion")}


@router.post("/{pid}/metadatos")
def generar_metadatos(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_metadatos")}


@router.post("/{pid}/voz")
def generar_voz(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_voz")}


@router.post("/{pid}/subtitulos")
def regenerar_subtitulos(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_subtitulos")}


@router.post("/{pid}/escenas")
def generar_escenas(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_escenas")}


@router.post("/{pid}/video")
def armar_video(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "armar_video")}


def _archivo(pid: int, partes: tuple[str, ...], media_type: str, detalle: str):
    try:
        ruta = proyectos_service.ruta_archivo(pid, *partes)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    if not ruta.exists():
        raise HTTPException(404, detalle)
    return FileResponse(ruta, media_type=media_type)


@router.get("/{pid}/audio")
def audio(pid: int):
    return _archivo(pid, ("voz.mp3",), "audio/mpeg", "Aún no hay voz generada")


@router.get("/{pid}/imagenes/{orden}")
def imagen(pid: int, orden: int):
    return _archivo(
        pid, ("imagenes", f"{orden:02d}.png"), "image/png", "Imagen no generada"
    )


@router.get("/{pid}/video")
def video(pid: int):
    return _archivo(pid, ("final.mp4",), "video/mp4", "Aún no hay video final")
