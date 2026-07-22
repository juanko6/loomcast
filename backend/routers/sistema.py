import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import COMFY_URL
from ..repositories import plantillas as plantillas_repo
from ..services import llm_runtime

router = APIRouter(prefix="/api", tags=["sistema"])


class SeleccionLLM(BaseModel):
    id: str


@router.get("/salud")
def salud():
    try:
        with httpx.Client(timeout=3) as c:
            comfy = c.get(f"{COMFY_URL}/system_stats").status_code < 400
    except httpx.HTTPError:
        comfy = False
    llm_estado = llm_runtime.estado()
    # `llm` es el booleano del semáforo: en un modelo gestionado, estar en
    # espera no es un fallo (se carga solo en la siguiente etapa de texto).
    return {
        "llm": llm_estado["estado"] != "caido",
        "comfy": comfy,
        "llm_estado": llm_estado,
    }


@router.get("/llm/modelos")
def listar_modelos():
    return {
        "activo": llm_runtime.activo().id,
        "modelos": [
            {"id": m.id, "nombre": m.nombre, "gestionado": m.gestionado}
            for m in llm_runtime.modelos()
        ],
    }


@router.post("/llm/modelo")
def elegir_modelo(sel: SeleccionLLM):
    try:
        modelo = llm_runtime.seleccionar(sel.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"id": modelo.id, "nombre": modelo.nombre}


@router.get("/plantillas")
def listar_plantillas():
    return plantillas_repo.listar()
