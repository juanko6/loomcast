from fastapi import APIRouter, HTTPException

from ..schemas import EstadoIdeaIn
from ..services import ideas as ideas_service

router = APIRouter(prefix="/api/ideas", tags=["ideas"])


@router.post("/{idea_id}/estado")
def cambiar_estado(idea_id: int, body: EstadoIdeaIn):
    try:
        ideas_service.cambiar_estado(idea_id, body.estado)
        return {"ok": True}
    except ideas_service.EstadoInvalido:
        raise HTTPException(400, "Estado inválido")
    except ideas_service.IdeaNoExiste:
        raise HTTPException(404, "Idea no existe")


@router.post("/{idea_id}/proyecto")
def crear_proyecto(idea_id: int):
    try:
        return ideas_service.crear_proyecto(idea_id)
    except ideas_service.IdeaNoExiste:
        raise HTTPException(404, "Idea no existe")
