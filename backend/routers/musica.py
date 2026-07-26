from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import MusicaCamposIn, MusicaGenerarIn, MusicaLanzarIn
from ..services import musica as musica_service
from ..services.pipeline import musica as musica_pipeline

router = APIRouter(prefix="/api/musica", tags=["musica"])

# Tipo MIME por extensión, para que el <audio> del navegador sepa reproducirlo.
_MIME = {
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".opus": "audio/opus",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}


@router.get("")
def listar():
    return musica_service.listar()


@router.post("")
def crear(body: MusicaGenerarIn):
    if not body.idea.strip() and not body.tags.strip():
        raise HTTPException(400, "Escribe una idea o unas etiquetas de estilo")
    return musica_service.crear(
        body.tipo, body.idea, body.tags, body.lyrics, body.duracion_s
    )


@router.get("/{musica_id}")
def detalle(musica_id: int):
    try:
        return musica_service.detalle(musica_id)
    except musica_service.MusicaNoExiste:
        raise HTTPException(404, "Música no existe")


@router.put("/{musica_id}")
def editar(musica_id: int, body: MusicaCamposIn):
    try:
        musica_service.editar_campos(
            musica_id, body.tags, body.lyrics, body.duracion_s
        )
        return {"ok": True}
    except musica_service.MusicaNoExiste:
        raise HTTPException(404, "Música no existe")


@router.post("/{musica_id}/mejorar")
def mejorar(musica_id: int):
    try:
        return {"job_id": musica_service.mejorar(musica_id)}
    except musica_service.MusicaNoExiste:
        raise HTTPException(404, "Música no existe")


@router.post("/{musica_id}/generar")
def generar(musica_id: int, body: MusicaLanzarIn | None = None):
    b = body or MusicaLanzarIn()
    try:
        return {
            "job_id": musica_service.generar(
                musica_id, b.tags, b.lyrics, b.duracion_s, b.seed
            )
        }
    except musica_service.MusicaNoExiste:
        raise HTTPException(404, "Música no existe")


@router.delete("/{musica_id}")
def borrar(musica_id: int):
    try:
        return musica_service.borrar(musica_id)
    except musica_service.MusicaNoExiste:
        raise HTTPException(404, "Música no existe")


@router.get("/{musica_id}/audio")
def audio(musica_id: int):
    ruta = musica_pipeline.ruta_audio(musica_id)
    if ruta is None:
        raise HTTPException(404, "Aún no hay audio generado")
    return FileResponse(ruta, media_type=_MIME.get(ruta.suffix.lower(), "audio/mpeg"))
