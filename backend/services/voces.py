"""Banco de voces: creación con VoiceDesign y consulta."""
import re
import unicodedata

from ..db import get_session
from ..repositories import voces as voces_repo
from ..workers import queue


class VozNoExiste(LookupError):
    pass


class SlugOcupado(ValueError):
    pass


def _slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:40] or "voz"


def listar() -> list[dict]:
    with get_session() as s:
        return [
            {
                "id": v.id, "slug": v.slug, "nombre": v.nombre,
                "instruct": v.instruct, "estado": v.estado,
                "disponible": voces_repo.ruta_ref(v.slug).exists(),
            }
            for v in voces_repo.listar(s)
        ]


def crear(nombre: str, instruct: str) -> dict:
    """Registra la voz y encola su generación con VoiceDesign."""
    slug = _slugify(nombre)
    with get_session() as s:
        if voces_repo.por_slug(s, slug):
            raise SlugOcupado(slug)
        voz = voces_repo.crear(s, slug, nombre.strip(), instruct.strip())
        s.commit()
        voz_id = voz.id
    job_id = queue.encolar("crear_voz", voz_id)
    return {"voz_id": voz_id, "slug": slug, "job_id": job_id}


def ruta_audio(slug: str):
    ref = voces_repo.ruta_ref(slug)
    if not ref.exists():
        raise VozNoExiste(slug)
    return ref
