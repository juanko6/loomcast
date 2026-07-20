"""API de Loomcast — Fase 1: tema → ideas → selección → guion → metadatos."""
import json
import re
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs, llm, plantillas
from .config import COMFY_URL, PROYECTOS_DIR
from .db import get_session, init_db
from .models import Guion, Idea, Job, Metadatos, Proyecto, Tema

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    jobs.arrancar_worker()
    jobs.recuperar_pendientes()
    yield


app = FastAPI(title="Loomcast", lifespan=lifespan)


def _slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60] or "proyecto"


# ---------- salud y plantillas ----------

@app.get("/api/salud")
def salud():
    try:
        with httpx.Client(timeout=3) as c:
            comfy = c.get(f"{COMFY_URL}/system_stats").status_code < 400
    except httpx.HTTPError:
        comfy = False
    return {"llm": llm.ping(), "comfy": comfy}


@app.get("/api/plantillas")
def listar_plantillas():
    return plantillas.listar()


# ---------- temas e ideas ----------

class TemaIn(BaseModel):
    texto: str
    plantilla: str = "curiosidades"


@app.post("/api/temas")
def crear_tema(body: TemaIn):
    if body.plantilla not in plantillas.listar():
        raise HTTPException(400, f"Plantilla desconocida: {body.plantilla}")
    with get_session() as s:
        tema = Tema(texto=body.texto.strip(), plantilla=body.plantilla)
        s.add(tema)
        s.commit()
        job_id = jobs.encolar("generar_ideas", tema.id)
        return {"tema_id": tema.id, "job_id": job_id}


@app.get("/api/temas")
def listar_temas():
    with get_session() as s:
        out = []
        for t in s.query(Tema).order_by(Tema.id.desc()).all():
            ideas = s.query(Idea).filter(Idea.tema_id == t.id).all()
            out.append({
                "id": t.id,
                "texto": t.texto,
                "plantilla": t.plantilla,
                "n_ideas": len(ideas),
                "n_aprobadas": sum(1 for i in ideas if i.estado == "aprobada"),
            })
        return out


@app.get("/api/temas/{tema_id}/ideas")
def ideas_de_tema(tema_id: int):
    with get_session() as s:
        proyectos = {
            p.idea_id: p.id for p in s.query(Proyecto).all()
        }
        return [
            {
                "id": i.id, "titulo": i.titulo, "gancho": i.gancho,
                "resumen": i.resumen, "estado": i.estado,
                "proyecto_id": proyectos.get(i.id),
            }
            for i in s.query(Idea).filter(Idea.tema_id == tema_id)
            .order_by(Idea.id).all()
        ]


@app.post("/api/temas/{tema_id}/ideas")
def mas_ideas(tema_id: int):
    with get_session() as s:
        if s.get(Tema, tema_id) is None:
            raise HTTPException(404, "Tema no existe")
    return {"job_id": jobs.encolar("generar_ideas", tema_id)}


class EstadoIdeaIn(BaseModel):
    estado: str  # propuesta | aprobada | descartada


@app.post("/api/ideas/{idea_id}/estado")
def cambiar_estado_idea(idea_id: int, body: EstadoIdeaIn):
    if body.estado not in ("propuesta", "aprobada", "descartada"):
        raise HTTPException(400, "Estado inválido")
    with get_session() as s:
        idea = s.get(Idea, idea_id)
        if idea is None:
            raise HTTPException(404, "Idea no existe")
        idea.estado = body.estado
        s.commit()
        return {"ok": True}


# ---------- proyectos ----------

@app.post("/api/ideas/{idea_id}/proyecto")
def crear_proyecto(idea_id: int):
    with get_session() as s:
        idea = s.get(Idea, idea_id)
        if idea is None:
            raise HTTPException(404, "Idea no existe")
        existente = s.query(Proyecto).filter(Proyecto.idea_id == idea_id).first()
        if existente:
            return {"proyecto_id": existente.id, "ya_existia": True}
        tema = s.get(Tema, idea.tema_id)
        base = _slugify(idea.titulo)
        slug = base
        n = 2
        while s.query(Proyecto).filter(Proyecto.slug == slug).first():
            slug = f"{base}-{n}"
            n += 1
        idea.estado = "aprobada"
        p = Proyecto(idea_id=idea_id, slug=slug, plantilla=tema.plantilla)
        s.add(p)
        s.commit()
        job_id = jobs.encolar("generar_guion", p.id)
        return {"proyecto_id": p.id, "job_id": job_id}


@app.get("/api/proyectos")
def listar_proyectos():
    with get_session() as s:
        out = []
        for p in s.query(Proyecto).order_by(Proyecto.id.desc()).all():
            idea = s.get(Idea, p.idea_id)
            out.append({
                "id": p.id, "slug": p.slug, "estado": p.estado,
                "plantilla": p.plantilla, "titulo": idea.titulo if idea else "",
            })
        return out


@app.get("/api/proyectos/{pid}")
def detalle_proyecto(pid: int):
    with get_session() as s:
        p = s.get(Proyecto, pid)
        if p is None:
            raise HTTPException(404, "Proyecto no existe")
        idea = s.get(Idea, p.idea_id)
        guion = (
            s.query(Guion).filter(Guion.proyecto_id == pid)
            .order_by(Guion.version.desc()).first()
        )
        meta = (
            s.query(Metadatos).filter(Metadatos.proyecto_id == pid)
            .order_by(Metadatos.version.desc()).first()
        )
        activos = (
            s.query(Job).filter(
                Job.ref_id == pid,
                Job.tipo.in_([
                    "generar_guion", "generar_metadatos",
                    "generar_voz", "generar_subtitulos",
                ]),
                Job.estado.in_(["pendiente", "corriendo"]),
            ).count()
        )
        base_dir = PROYECTOS_DIR / p.slug
        srt = base_dir / "subtitulos.srt"
        return {
            "id": p.id, "slug": p.slug, "estado": p.estado,
            "plantilla": p.plantilla,
            "idea": {"titulo": idea.titulo, "gancho": idea.gancho,
                     "resumen": idea.resumen} if idea else None,
            "guion": json.loads(guion.contenido) if guion else None,
            "guion_version": guion.version if guion else 0,
            "metadatos": json.loads(meta.contenido) if meta else None,
            "voz_disponible": (base_dir / "voz.mp3").exists(),
            "subtitulos": srt.read_text() if srt.exists() else None,
            "jobs_activos": activos,
        }


class GuionIn(BaseModel):
    gancho: str
    frases: list[str]
    cta: str


@app.put("/api/proyectos/{pid}/guion")
def editar_guion(pid: int, body: GuionIn):
    with get_session() as s:
        p = s.get(Proyecto, pid)
        if p is None:
            raise HTTPException(404, "Proyecto no existe")
        version = 1 + len(s.query(Guion).filter(Guion.proyecto_id == pid).all())
        s.add(Guion(
            proyecto_id=pid, version=version,
            contenido=json.dumps(body.model_dump(), ensure_ascii=False),
        ))
        if p.estado == "IDEA":
            p.estado = "GUION"
        s.commit()
        return {"version": version}


@app.post("/api/proyectos/{pid}/guion/regenerar")
def regenerar_guion(pid: int):
    return {"job_id": jobs.encolar("generar_guion", pid)}


@app.post("/api/proyectos/{pid}/metadatos")
def generar_metadatos(pid: int):
    return {"job_id": jobs.encolar("generar_metadatos", pid)}


@app.post("/api/proyectos/{pid}/voz")
def generar_voz(pid: int):
    return {"job_id": jobs.encolar("generar_voz", pid)}


@app.post("/api/proyectos/{pid}/subtitulos")
def regenerar_subtitulos(pid: int):
    return {"job_id": jobs.encolar("generar_subtitulos", pid)}


@app.get("/api/proyectos/{pid}/audio")
def audio_proyecto(pid: int):
    with get_session() as s:
        p = s.get(Proyecto, pid)
        if p is None:
            raise HTTPException(404, "Proyecto no existe")
        mp3 = PROYECTOS_DIR / p.slug / "voz.mp3"
    if not mp3.exists():
        raise HTTPException(404, "Aún no hay voz generada")
    return FileResponse(mp3, media_type="audio/mpeg")


# ---------- jobs ----------

@app.get("/api/jobs/{job_id}")
def ver_job(job_id: int):
    with get_session() as s:
        j = s.get(Job, job_id)
        if j is None:
            raise HTTPException(404, "Job no existe")
        return {"id": j.id, "tipo": j.tipo, "ref_id": j.ref_id,
                "estado": j.estado, "log": j.log}


@app.get("/api/jobs")
def jobs_activos():
    with get_session() as s:
        return [
            {"id": j.id, "tipo": j.tipo, "ref_id": j.ref_id, "estado": j.estado}
            for j in s.query(Job)
            .filter(Job.estado.in_(["pendiente", "corriendo"]))
            .order_by(Job.id).all()
        ]


# ---------- frontend ----------

@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
