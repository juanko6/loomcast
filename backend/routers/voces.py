from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import VozNuevaIn
from ..services import voces as voces_service

router = APIRouter(prefix="/api/voces", tags=["voces"])


@router.get("")
def listar():
    return voces_service.listar()


@router.post("")
def crear(body: VozNuevaIn):
    try:
        return voces_service.crear(body.nombre, body.instruct)
    except voces_service.SlugOcupado as e:
        raise HTTPException(409, f"Ya existe una voz con nombre similar: {e}")


@router.get("/{slug}/audio")
def audio(slug: str):
    try:
        return FileResponse(voces_service.ruta_audio(slug), media_type="audio/wav")
    except voces_service.VozNoExiste:
        raise HTTPException(404, "Voz no disponible")
