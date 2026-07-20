import httpx
from fastapi import APIRouter

from ..clients import llm
from ..config import COMFY_URL
from ..repositories import plantillas as plantillas_repo

router = APIRouter(prefix="/api", tags=["sistema"])


@router.get("/salud")
def salud():
    try:
        with httpx.Client(timeout=3) as c:
            comfy = c.get(f"{COMFY_URL}/system_stats").status_code < 400
    except httpx.HTTPError:
        comfy = False
    return {"llm": llm.ping(), "comfy": comfy}


@router.get("/plantillas")
def listar_plantillas():
    return plantillas_repo.listar()
