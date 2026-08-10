from fastapi import APIRouter, HTTPException

from ..db import get_session
from ..repositories import jobs as jobs_repo
from ..services import progreso

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _progreso_de(job_id: int) -> dict | None:
    """El progreso del job solo si es el que está corriendo ahora mismo: la
    cola procesa de uno en uno, así que los demás no tienen ninguno."""
    p = progreso.snapshot()
    return p if p and p["job_id"] == job_id else None


@router.get("/{job_id}")
def ver_job(job_id: int):
    with get_session() as s:
        j = jobs_repo.obtener(s, job_id)
        if j is None:
            raise HTTPException(404, "Job no existe")
        return {"id": j.id, "tipo": j.tipo, "ref_id": j.ref_id,
                "estado": j.estado, "log": j.log,
                "progreso": _progreso_de(j.id)}


@router.get("")
def jobs_activos():
    with get_session() as s:
        return [
            {"id": j.id, "tipo": j.tipo, "ref_id": j.ref_id, "estado": j.estado,
             "progreso": _progreso_de(j.id)}
            for j in jobs_repo.activos(s)
        ]
