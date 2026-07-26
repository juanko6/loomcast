"""Punto de entrada: crea la app, monta routers y el frontend estático."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .db import init_db
from .routers import galeria, ideas, jobs, musica, proyectos, sistema, temas, voces
from .services import llm_runtime
from .workers import queue

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


class NoCacheStatic(StaticFiles):
    """Sirve el frontend forzando revalidación: al iterar rápido, el navegador
    no debe quedarse con app.js/style.css viejos en caché."""

    def file_response(self, *args, **kwargs) -> Response:
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    llm_runtime.arrancar()
    queue.arrancar_worker()
    queue.recuperar_pendientes()
    yield
    # No dejar un llama-server huérfano ocupando la RAM tras cerrar Loomcast.
    llm_runtime.apagar()


app = FastAPI(title="Loomcast", lifespan=lifespan)

app.include_router(sistema.router)
app.include_router(temas.router)
app.include_router(ideas.router)
app.include_router(voces.router)
app.include_router(proyectos.router)
app.include_router(jobs.router)
app.include_router(galeria.router)
app.include_router(musica.router)


@app.get("/")
def index():
    return FileResponse(
        FRONTEND / "index.html", headers={"Cache-Control": "no-cache, must-revalidate"}
    )


app.mount("/static", NoCacheStatic(directory=FRONTEND), name="static")
