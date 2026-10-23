"""Banco de voces: creación con VoiceDesign, clonado de audio real y consulta.

El banco es el único almacén de voces del proyecto, y por eso lo usan también
las voces de los personajes (ver `instruct_desde_ficha`): una voz del banco ya
se escucha, se reutiliza entre vídeos y se borra desde un sitio, así que montar
un segundo almacén en paralelo para el reparto solo duplicaría ese trabajo.
"""
import itertools
import re
import shutil
import unicodedata
from pathlib import Path

from ..config import VOCES_DIR
from ..db import get_session
from ..repositories import jobs as jobs_repo
from ..repositories import personajes as personajes_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import reparto as reparto_repo
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


def _slug_libre(s, base: str) -> str:
    """`base` si nadie la usa, y si no base-2, base-3…"""
    if voces_repo.por_slug(s, base) is None:
        return base
    return next(
        c for c in (f"{base}-{n}" for n in itertools.count(2))
        if voces_repo.por_slug(s, c) is None
    )


def instruct_desde_ficha(nombre: str, ficha: str, tipo: str = "persona") -> str:
    """Instrucción de VoiceDesign para un personaje, escrita desde su ficha.

    La ficha es el mismo material del que sale su retrato, y dice la edad
    aparente, el género y el aire del personaje: justo lo que decide el timbre.
    Se redacta con los cuatro bloques que VoiceDesign interpreta bien (perfil,
    emoción, ritmo y contexto) porque una sola frase de timbre da voces planas;
    los tres últimos son fijos y describen a alguien **diciendo** sus líneas
    dentro de una historia, no narrándola, que es para lo que se usa.

    Es un punto de partida, no una verdad: la voz queda en el banco como
    cualquier otra, se escucha y, si no convence, se borra y se crea a mano con
    otra descripción.
    """
    quien = (nombre or "el personaje").strip()
    ficha = " ".join((ficha or "").split()).rstrip(" .")
    if (tipo or "").strip().lower().startswith("obj"):
        perfil = (
            f"Voz en español de {quien}, que no es una persona sino esto: "
            f"{ficha}. Dale un timbre con carácter que encaje con esa materia y "
            "ese tamaño, sin sonar a robot de dibujos."
        )
    else:
        perfil = (
            f"Voz en español de {quien}, cuya ficha física es: {ficha}. La edad "
            "aparente, el género y el aire que se oigan son los de esa ficha."
        )
    return (
        f"[PERFIL DE VOZ] {perfil}\n"
        "[EMOCIÓN Y ACTITUD] Habla desde dentro de la historia, con la emoción "
        "de lo que está diciendo; no presenta ni narra: interviene.\n"
        "[DINÁMICA Y RITMO] Ritmo de alguien hablando, no de alguien leyendo: "
        "frases cortas, sin cadencia de locutor.\n"
        "[INDICACIONES DE CONTEXTO] Dice una o dos líneas sueltas dentro de un "
        "relato que lleva otra voz, así que tiene que distinguirse de ella desde "
        "la primera palabra."
    )


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


def registrar_para_personaje(nombre: str, instruct: str) -> dict:
    """Da de alta en el banco la voz de un personaje, **sin encolar nada**.

    Busca slug libre en vez de rechazar el repetido: esto no es un alta a mano,
    y dos vídeos pueden tener cada uno su Ana. Fallar con "ya existe una voz con
    nombre similar" obligaría a bautizarla justo cuando el nombre da igual: lo
    que la identifica es el personaje al que está pegada.

    Separado de `crear_para_personaje` porque la etapa de voz sintetiza ella
    misma el clip de los personajes a los que les escribe la voz: ya tiene el
    VoiceDesign cargado para eso, y pasar por la cola sería volver a cargarlo
    una vez por personaje.
    """
    nombre = nombre.strip() or "personaje"
    with get_session() as s:
        slug = _slug_libre(s, _slugify(nombre))
        voz = voces_repo.crear(s, slug, nombre, instruct.strip())
        s.commit()
        return {"voz_id": voz.id, "slug": slug}


def crear_para_personaje(nombre: str, instruct: str) -> dict:
    """La registra y encola su síntesis: es el botón "crear su voz desde la
    ficha", el que se pulsa para rehacer una voz que no convenció."""
    creada = registrar_para_personaje(nombre, instruct)
    return {**creada, "job_id": queue.encolar("crear_voz", creada["voz_id"])}


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
    """Borra la voz del banco: su fila y su carpeta en disco.

    Deja sin voz a los tres que podían estar usándola —los proyectos que
    narraban con ella, los personajes que decían sus líneas con ella y los
    miembros del reparto propio que se la llevaban a cada vídeo nuevo—, porque
    una referencia colgada a un `ref.wav` que ya no está no falla: enmudece. No
    se puede borrar mientras se está generando.
    """
    with get_session() as s:
        voz = voces_repo.por_slug(s, slug)
        if voz is None:
            raise VozNoExiste(slug)
        if jobs_repo.activos_de_voz(s, voz.id):
            raise VozOcupada(slug)
        desvinculados = proyectos_repo.desvincular_voz(s, slug)
        personajes = personajes_repo.desvincular_voz(s, slug)
        miembros = reparto_repo.desvincular_voz(s, slug)
        voces_repo.borrar(s, voz)
        s.commit()

    carpeta = VOCES_DIR / slug
    if carpeta.exists():
        shutil.rmtree(carpeta)
    return {
        "slug": slug,
        "proyectos_desvinculados": desvinculados,
        "personajes_desvinculados": personajes,
        "reparto_desvinculado": miembros,
    }


def ruta_audio(slug: str):
    ref = voces_repo.ruta_ref(slug)
    if not ref.exists():
        raise VozNoExiste(slug)
    return ref
