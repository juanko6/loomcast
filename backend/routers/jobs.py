from fastapi import APIRouter, HTTPException

from ..schemas import ParadaIn
from ..services import jobs as jobs_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def jobs_activos():
    return jobs_service.activos()


@router.get("/historial")
def historial(limite: int = 20):
    return jobs_service.historial(max(1, min(limite, 100)))


@router.post("/parar")
def parar(datos: ParadaIn | None = None):
    d = datos or ParadaIn()
    return jobs_service.parar(d.corriendo, d.pendientes)


@router.post("/{job_id}/cancelar")
def cancelar(job_id: int):
    try:
        return jobs_service.cancelar(job_id)
    except jobs_service.JobNoExiste:
        raise HTTPException(404, "Job no existe")


@router.get("/{job_id}")
def ver_job(job_id: int):
    try:
        return jobs_service.ver(job_id)
    except jobs_service.JobNoExiste:
        raise HTTPException(404, "Job no existe")
