"""Lógica de negocio de ideas: aprobación y conversión a proyecto."""
import re
import unicodedata

from ..db import get_session
from ..repositories import ideas as ideas_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import series as series_repo
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


def crear_proyecto(idea_id: int, encolar_guion: bool = True) -> dict:
    """Aprueba la idea, crea el proyecto con slug único y encola el guion.

    Si el tema de la idea es el de una serie, el proyecto nace como su episodio
    siguiente: hereda la plantilla de la serie, se numera y se le trae el
    reparto fijo antes de escribir el guion, que es lo que ese guion necesita
    saber. Para un tema sin serie no cambia nada de lo que hacía.

    `encolar_guion=False` lo deja recién nacido y sin nada en la cola: lo usa el
    lote, donde el guion lo encola el autopiloto de cada proyecto cuando le toca
    su turno. Si lo encolara aquí, lanzar un lote de diez metería los diez
    guiones de golpe y el lote dejaría de producirse de uno en uno.
    """
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
        serie = series_repo.por_tema(s, idea.tema_id)
        p = proyectos_repo.crear(
            s, idea_id, slug,
            # La plantilla de la serie manda sobre la del tema: es la que decide
            # el formato de guion con líneas de personaje y los ocho prompts.
            serie.plantilla if serie else tema.plantilla,
        )
        if serie is not None:
            p.serie_id = serie.id
            s.flush()
            p.episodio = series_repo.siguiente_numero(s, serie.id)
        s.commit()
        proyecto_id = p.id

    # Importado aquí dentro porque el servicio de series llama a este para crear
    # el episodio: a nivel de módulo el ciclo sería real. Para un proyecto sin
    # serie devuelve lista vacía y no toca nada.
    from ..services import series as series_service

    traidos = series_service.traer_reparto_fijo(proyecto_id)
    job_id = queue.encolar("generar_guion", proyecto_id) if encolar_guion else None
    return {"proyecto_id": proyecto_id, "job_id": job_id,
            "reparto_traido": [x["clave"] for x in traidos]}
