"""Punto de entrada: crea la app, monta routers y el frontend estático."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .db import init_db
from .routers import (
    galeria,
    ideas,
    jobs,
    lotes,
    musica,
    proyectos,
    reparto,
    series,
    sistema,
    temas,
    voces,
)
from .services import llm_runtime
from .workers import queue

# Build estático del frontend (Astro). Se genera con `pnpm build` en `web/`.
FRONTEND = Path(__file__).resolve().parent.parent / "web" / "dist"
INDEX = FRONTEND / "index.html"

FALTA_BUILD = (
    "<h1>Falta compilar el frontend</h1>"
    "<p>Ejecuta <code>pnpm install &amp;&amp; pnpm build</code> dentro de "
    "<code>web/</code> y recarga.</p>"
    "<p>Para desarrollar el frontend con recarga en caliente: "
    "<code>pnpm dev</code> (Astro en 4321, con proxy de <code>/api</code> "
    "hacia este servidor).</p>"
)


class AppStatic(StaticFiles):
    """Sirve el build. Los assets de Astro ya llevan hash en el nombre, así que
    pueden cachearse; el HTML debe revalidar para no servir un índice viejo que
    apunte a assets que ya no existen."""

    def file_response(self, *args, **kwargs) -> Response:
        resp = super().file_response(*args, **kwargs)
        if resp.headers.get("content-type", "").startswith("text/html"):
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
app.include_router(reparto.router)
app.include_router(series.router)
app.include_router(proyectos.router)
app.include_router(jobs.router)
app.include_router(lotes.router)
app.include_router(galeria.router)
app.include_router(musica.router)


@app.get("/")
def index():
    if not INDEX.exists():
        return HTMLResponse(FALTA_BUILD, status_code=503)
    return FileResponse(INDEX, headers={"Cache-Control": "no-cache, must-revalidate"})


# El montaje va al final: los routers de /api ya están registrados y se
# resuelven antes. Solo se monta si hay build, para que la ayuda de arriba se
# vea en vez de reventar al arrancar.
if FRONTEND.is_dir():
    app.mount("/", AppStatic(directory=FRONTEND, html=True), name="app")
