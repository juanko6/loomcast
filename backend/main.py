"""Punto de entrada: crea la app, monta routers y el frontend estático."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import ideas, jobs, proyectos, sistema, temas
from .workers import queue

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    queue.arrancar_worker()
    queue.recuperar_pendientes()
    yield


app = FastAPI(title="Loomcast", lifespan=lifespan)

app.include_router(sistema.router)
app.include_router(temas.router)
app.include_router(ideas.router)
app.include_router(proyectos.router)
app.include_router(jobs.router)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
