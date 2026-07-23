"""Banco de voces: creación con VoiceDesign, clonado de audio real y consulta."""
import re
import shutil
import unicodedata
from pathlib import Path

from ..config import VOCES_DIR
from ..db import get_session
from ..repositories import jobs as jobs_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import voces as voces_repo
from ..workers import queue

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus", ".webm"}
MAX_AUDIO_BYTES = 30 * 1024 * 1024  # 30 MB


class VozNoExiste(LookupError):
    pass


class SlugOcupado(ValueError):
    pass


class AudioInvalido(ValueError):
    pass


class VozOcupada(RuntimeError):
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


def crear_clon(nombre: str, filename: str, data: bytes, descripcion: str = "",
               inicio: float = 0.0, fin: float | None = None) -> dict:
    """Registra una voz clonada de un audio real y encola su procesado
    (recortar [inicio, fin] + convertir + transcribir). No usa VoiceDesign:
    la voz sale del propio clip."""
    nombre = nombre.strip()
    if not nombre:
        raise AudioInvalido("Falta el nombre de la voz")
    ext = Path(filename).suffix.lower()
    if ext not in AUDIO_EXTS:
        raise AudioInvalido(f"Formato de audio no soportado: {ext or 'desconocido'}")
    if not data:
        raise AudioInvalido("El archivo de audio está vacío")
    if len(data) > MAX_AUDIO_BYTES:
        raise AudioInvalido("El audio supera el máximo de 30 MB")

    slug = _slugify(nombre)
    with get_session() as s:
        if voces_repo.por_slug(s, slug):
            raise SlugOcupado(slug)
        instruct = descripcion.strip() or "Clonada desde un audio de referencia."
        voz = voces_repo.crear(s, slug, nombre, instruct)
        s.commit()
        voz_id = voz.id

    base = VOCES_DIR / slug
    base.mkdir(parents=True, exist_ok=True)
    for viejo in base.glob("origen.*"):
        viejo.unlink()
    (base / f"origen{ext}").write_bytes(data)

    job_id = queue.encolar(
        "clonar_voz", voz_id,
        inicio=float(inicio or 0.0),
        fin=(float(fin) if fin is not None else None),
    )
    return {"voz_id": voz_id, "slug": slug, "job_id": job_id}


def borrar(slug: str) -> dict:
    """Borra la voz del banco: su fila y su carpeta en disco. Deja sin voz los
    proyectos que la usaban. No se puede borrar mientras se está generando."""
    with get_session() as s:
        voz = voces_repo.por_slug(s, slug)
        if voz is None:
            raise VozNoExiste(slug)
        if jobs_repo.activos_de_voz(s, voz.id):
            raise VozOcupada(slug)
        desvinculados = proyectos_repo.desvincular_voz(s, slug)
        voces_repo.borrar(s, voz)
        s.commit()

    carpeta = VOCES_DIR / slug
    if carpeta.exists():
        shutil.rmtree(carpeta)
    return {"slug": slug, "proyectos_desvinculados": desvinculados}


def ruta_audio(slug: str):
    ref = voces_repo.ruta_ref(slug)
    if not ref.exists():
        raise VozNoExiste(slug)
    return ref
