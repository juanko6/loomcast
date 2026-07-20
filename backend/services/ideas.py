"""Lógica de negocio de ideas: aprobación y conversión a proyecto."""
import re
import unicodedata

from ..db import get_session
from ..repositories import ideas as ideas_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import temas as temas_repo
from ..workers import queue

ESTADOS_VALIDOS = ("propuesta", "aprobada", "descartada")


class IdeaNoExiste(LookupError):
    pass


class EstadoInvalido(ValueError):
    pass


def _slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60] or "proyecto"


def cambiar_estado(idea_id: int, estado: str) -> None:
    if estado not in ESTADOS_VALIDOS:
        raise EstadoInvalido(estado)
    with get_session() as s:
        idea = ideas_repo.obtener(s, idea_id)
        if idea is None:
            raise IdeaNoExiste(idea_id)
        idea.estado = estado
        s.commit()


def crear_proyecto(idea_id: int) -> dict:
    """Aprueba la idea, crea el proyecto con slug único y encola el guion."""
    with get_session() as s:
        idea = ideas_repo.obtener(s, idea_id)
        if idea is None:
            raise IdeaNoExiste(idea_id)
        existente = proyectos_repo.por_idea(s, idea_id)
        if existente:
            return {"proyecto_id": existente.id, "ya_existia": True}

        tema = temas_repo.obtener(s, idea.tema_id)
        base = _slugify(idea.titulo)
        slug, n = base, 2
        while proyectos_repo.slug_existe(s, slug):
            slug = f"{base}-{n}"
            n += 1
        idea.estado = "aprobada"
        p = proyectos_repo.crear(s, idea_id, slug, tema.plantilla)
        s.commit()
        proyecto_id = p.id
    job_id = queue.encolar("generar_guion", proyecto_id)
    return {"proyecto_id": proyecto_id, "job_id": job_id}
