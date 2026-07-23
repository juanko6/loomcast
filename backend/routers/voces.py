from fastapi import APIRouter, File, Form, HTTPException, UploadFile
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


@router.post("/clonar")
async def clonar(
    nombre: str = Form(...),
    audio: UploadFile = File(...),
    descripcion: str = Form(""),
    inicio: float = Form(0.0),
    fin: float | None = Form(None),
):
    data = await audio.read()
    try:
        return voces_service.crear_clon(
            nombre, audio.filename or "", data, descripcion, inicio, fin
        )
    except voces_service.SlugOcupado as e:
        raise HTTPException(409, f"Ya existe una voz con nombre similar: {e}")
    except voces_service.AudioInvalido as e:
        raise HTTPException(400, str(e))


@router.delete("/{slug}")
def borrar(slug: str):
    try:
        return voces_service.borrar(slug)
    except voces_service.VozNoExiste:
        raise HTTPException(404, "Voz no encontrada")
    except voces_service.VozOcupada:
        raise HTTPException(409, "La voz se está generando; espera a que termine")


@router.get("/{slug}/audio")
def audio(slug: str):
    try:
        return FileResponse(voces_service.ruta_audio(slug), media_type="audio/wav")
    except voces_service.VozNoExiste:
        raise HTTPException(404, "Voz no disponible")
