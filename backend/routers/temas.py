from fastapi import APIRouter, HTTPException

from ..schemas import TemaIn
from ..services import temas as temas_service

router = APIRouter(prefix="/api/temas", tags=["temas"])


@router.post("")
def crear_tema(body: TemaIn):
    try:
        return temas_service.crear_tema(body.texto, body.plantilla)
    except temas_service.PlantillaInvalida as e:
        raise HTTPException(400, f"Plantilla desconocida: {e}")


@router.get("")
def listar_temas():
    return temas_service.listar_temas()


@router.get("/{tema_id}/ideas")
def ideas_de_tema(tema_id: int):
    return temas_service.ideas_de_tema(tema_id)


@router.post("/{tema_id}/ideas")
def mas_ideas(tema_id: int):
    try:
        return {"job_id": temas_service.pedir_mas_ideas(tema_id)}
    except temas_service.TemaNoExiste:
        raise HTTPException(404, "Tema no existe")


@router.delete("/{tema_id}")
def borrar_tema(tema_id: int):
    """Borra el tema y sus ideas. Falla si alguna idea ya es un proyecto."""
    try:
        return temas_service.borrar_tema(tema_id)
    except temas_service.TemaNoExiste:
        raise HTTPException(404, "Tema no existe")
    except temas_service.TemaConProyectos as e:
        raise HTTPException(409, "Hay proyectos creados desde este tema: "
                                 f"{', '.join(e.titulos)}. Bórralos primero.")
