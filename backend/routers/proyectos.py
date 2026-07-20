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


@router.get("/{pid}/audio")
def audio(pid: int):
    try:
        mp3 = proyectos_service.ruta_audio(pid)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    if not mp3.exists():
        raise HTTPException(404, "Aún no hay voz generada")
    return FileResponse(mp3, media_type="audio/mpeg")
