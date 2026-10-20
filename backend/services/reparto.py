"""Reparto propio: personajes reutilizables entre vídeos.

Un `Personaje` cuelga de su proyecto y muere con él, así que el mismo narrador
recurrente había que describirlo y retratarlo en cada vídeo, y salía distinto.
Aquí vive el reparto de la casa: se promueve a alguien que ya quedó bien en un
proyecto y se trae a los siguientes con la ficha y la cara ya fijadas.

Dos decisiones de diseño que explican casi todo lo de abajo:

- **Al traer a alguien, su retrato se copia; no se referencia.** Los proyectos
  son autocontenidos en disco (`proyectos/<slug>/` lleva todo lo suyo) y eso ha
  salido bien: borrar de aquí no puede romper un vídeo ya hecho ni cambiar un
  proyecto antiguo por detrás.
- **Editar la ficha dentro de un proyecto no toca al original.** Un retoque para
  una escena concreta no debe cambiar al personaje en todos los vídeos futuros:
  para eso hay que pedirlo (`actualizar`), que es una acción aparte.
- **Su voz viaja con él, pero no se copia.** La cara es un PNG del proyecto y la
  voz es una fila del banco, que ya es compartida entre vídeos: lo que viaja es
  el slug. Si esa voz se borró del banco, el personaje entra sin voz en vez de
  apuntar a un `ref.wav` que no está.

A diferencia del banco de voces, aquí no se encola nada: promover y traer son
copiar un PNG y escribir una fila, sin GPU ni LLM de por medio, así que van en
el hilo HTTP y la UI ve el resultado al instante.
"""
import re
import shutil
import unicodedata

from ..db import get_session
from ..repositories import personajes as personajes_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import reparto as reparto_repo
from ..repositories import voces as voces_repo
from ..services.pipeline import retratos


class MiembroNoExiste(LookupError):
    pass


class SlugOcupado(ValueError):
    pass


class ProyectoNoExiste(LookupError):
    pass


class PersonajeNoExiste(LookupError):
    pass


class SinFicha(ValueError):
    pass


def _slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:40] or "miembro"


def _dict(m) -> dict:
    return {
        "slug": m.slug, "nombre": m.nombre, "clave": m.clave,
        "ficha": m.ficha, "tipo": m.tipo or "persona",
        "voz": m.voz or "",
        "retrato": reparto_repo.ruta_retrato(m.slug).exists(),
    }


def listar() -> list[dict]:
    with get_session() as s:
        return [_dict(m) for m in reparto_repo.listar(s)]


def _personaje(s, proyecto_id: int, clave: str):
    """El personaje `clave` del proyecto, validando las dos cosas.

    La clave llega en el cuerpo de la petición y acaba formando una ruta de
    archivo, así que no se compone sin comprobar que es uno del reparto.
    """
    p = proyectos_repo.obtener(s, proyecto_id)
    if p is None:
        raise ProyectoNoExiste(proyecto_id)
    personaje = next(
        (x for x in personajes_repo.por_proyecto(s, proyecto_id) if x.clave == clave),
        None,
    )
    if personaje is None:
        raise PersonajeNoExiste(clave)
    return p, personaje


def _copiar_retrato(origen, destino) -> bool:
    if not origen.exists():
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return True


def promover(proyecto_id: int, clave: str, nombre: str = "") -> dict:
    """Guarda en el reparto propio a un personaje de un proyecto.

    El alta es así y no un formulario en blanco porque el momento en que uno
    sabe que quiere conservar a alguien es cuando ya tiene su ficha afinada y un
    retrato que convence, y eso pasa dentro de un proyecto.

    El retrato se copia si existe; si no, el miembro se guarda igual (la ficha
    es la mitad del trabajo) y se le genera cara en el primer proyecto al que se
    traiga.
    """
    with get_session() as s:
        proyecto, personaje = _personaje(s, proyecto_id, clave)
        if not personaje.ficha.strip():
            raise SinFicha(clave)
        nombre = (nombre or personaje.nombre or clave).strip()
        slug = _slugify(nombre)
        if reparto_repo.por_slug(s, slug):
            raise SlugOcupado(slug)
        reparto_repo.crear(s, slug, nombre, personaje.clave,
                           personaje.ficha, personaje.tipo or "persona",
                           personaje.seed, personaje.voz or "")
        # Queda enlazado para que la UI ofrezca "actualizar en el reparto" en vez
        # de volver a promoverlo y acabar con dos copias del mismo narrador.
        personaje.reparto_slug = slug
        proyecto_slug = proyecto.slug
        s.commit()

    con_retrato = _copiar_retrato(
        retratos.ruta_retrato(proyecto_slug, clave),
        reparto_repo.ruta_retrato(slug),
    )
    return {"slug": slug, "nombre": nombre, "retrato": con_retrato}


def actualizar(slug: str, proyecto_id: int, clave: str) -> dict:
    """Pisa al miembro del reparto con la versión que hay en un proyecto.

    Es la vía explícita que hace falta porque editar la ficha dentro de un
    proyecto **no** toca al original: retocar a alguien para una escena no puede
    cambiarlo en todos los vídeos futuros. Cuando el retoque sí era una mejora
    de verdad, se promueve de nuevo desde aquí.

    Los proyectos que ya se lo trajeron no cambian: lo suyo son copias.
    """
    with get_session() as s:
        m = reparto_repo.por_slug(s, slug)
        if m is None:
            raise MiembroNoExiste(slug)
        proyecto, personaje = _personaje(s, proyecto_id, clave)
        if not personaje.ficha.strip():
            raise SinFicha(clave)
        m.ficha = personaje.ficha
        m.tipo = personaje.tipo or "persona"
        m.seed = personaje.seed
        m.clave = personaje.clave
        m.voz = personaje.voz or ""
        personaje.reparto_slug = slug
        proyecto_slug, nombre = proyecto.slug, m.nombre
        s.commit()

    con_retrato = _copiar_retrato(
        retratos.ruta_retrato(proyecto_slug, clave),
        reparto_repo.ruta_retrato(slug),
    )
    return {"slug": slug, "nombre": nombre, "retrato": con_retrato}


def traer(slug: str, proyecto_id: int) -> dict:
    """Mete a un miembro del reparto propio en un proyecto, con su cara.

    La clave puede estar ocupada por alguien del casting, y las claves son
    marcadores ya escritos en los prompts de escena: en ese caso se le da la
    siguiente libre (ANA_2) en vez de pisar al que estaba. La respuesta dice con
    qué clave entró para que la UI lo avise, porque es la que hay que escribir
    en los prompts.
    """
    with get_session() as s:
        m = reparto_repo.por_slug(s, slug)
        if m is None:
            raise MiembroNoExiste(slug)
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ProyectoNoExiste(proyecto_id)
        clave = personajes_repo.clave_libre(s, proyecto_id, m.clave)
        # La voz solo entra si sigue en el banco: borrarla de allí la pierde
        # para todos, y meter el slug de una voz que ya no existe dejaría sus
        # líneas mudas sin decir por qué.
        voz = m.voz if m.voz and voces_repo.por_slug(s, m.voz) else ""
        personajes_repo.crear(s, proyecto_id, clave, m.nombre, m.ficha,
                              m.seed, m.tipo or "persona", reparto_slug=slug,
                              voz=voz)
        s.commit()
        proyecto_slug, renombrado = p.slug, clave != m.clave

    con_retrato = _copiar_retrato(
        reparto_repo.ruta_retrato(slug),
        retratos.ruta_retrato(proyecto_slug, clave),
    )
    return {"clave": clave, "renombrado": renombrado, "retrato": con_retrato,
            "voz": voz}


def borrar(slug: str) -> dict:
    """Saca a alguien del reparto propio: su fila y su carpeta.

    Los proyectos que se lo trajeron no se tocan —tienen su copia de la ficha y
    del retrato— y solo olvidan de dónde vino.
    """
    with get_session() as s:
        m = reparto_repo.por_slug(s, slug)
        if m is None:
            raise MiembroNoExiste(slug)
        desvinculados = reparto_repo.desvincular(s, slug)
        reparto_repo.borrar(s, m)
        s.commit()

    carpeta = reparto_repo.carpeta(slug)
    if carpeta.exists():
        shutil.rmtree(carpeta)
    return {"slug": slug, "personajes_desvinculados": desvinculados}


def ruta_retrato(slug: str):
    with get_session() as s:
        if reparto_repo.por_slug(s, slug) is None:
            raise MiembroNoExiste(slug)
    ruta = reparto_repo.ruta_retrato(slug)
    if not ruta.exists():
        raise MiembroNoExiste(slug)
    return ruta
