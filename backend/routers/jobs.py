from fastapi import APIRouter, HTTPException

from ..db import get_session
from ..repositories import jobs as jobs_repo

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def ver_job(job_id: int):
    with get_session() as s:
        j = jobs_repo.obtener(s, job_id)
        if j is None:
            raise HTTPException(404, "Job no existe")
        return {"id": j.id, "tipo": j.tipo, "ref_id": j.ref_id,
                "estado": j.estado, "log": j.log}


@router.get("")
def jobs_activos():
    with get_session() as s:
        return [
            {"id": j.id, "tipo": j.tipo, "ref_id": j.ref_id, "estado": j.estado}
            for j in jobs_repo.activos(s)
        ]
