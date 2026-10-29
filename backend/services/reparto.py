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
import itertools
import re
import shutil
import unicodedata

from ..db import get_session
from ..repositories import personajes as personajes_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import reparto as reparto_repo
from ..repositories import series as series_repo
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


class VozNoExiste(LookupError):
    pass


def _slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:40] or "miembro"


def _slug_libre(s, base: str) -> str:
    """`base` si nadie la usa, y si no base-2, base-3…

    Al promover a alguien, el slug repetido se rechaza: estás guardando a una
    persona concreta y dos "Ana" en la lista no se distinguen. Al ficharlos
    desde el hilo no hay nadie delante para rebautizarlos, y dos series pueden
    tener cada una su Marta, así que ahí se busca sitio en vez de fallar.
    """
    if reparto_repo.por_slug(s, base) is None:
        return base
    return next(
        c for c in (f"{base}-{n}" for n in itertools.count(2))
        if reparto_repo.por_slug(s, c) is None
    )


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
    del retrato— y solo olvidan de dónde vino. Las series en cuyo reparto fijo
    estaba sí tienen que soltarlo: esas filas son la orden de traerlo a cada
    episodio nuevo, y dejarlas rompería la creación del siguiente.
    """
    with get_session() as s:
        m = reparto_repo.por_slug(s, slug)
        if m is None:
            raise MiembroNoExiste(slug)
        desvinculados = reparto_repo.desvincular(s, slug)
        series_sueltas = series_repo.desvincular_reparto(s, slug)
        reparto_repo.borrar(s, m)
        s.commit()

    carpeta = reparto_repo.carpeta(slug)
    if carpeta.exists():
        shutil.rmtree(carpeta)
    return {"slug": slug, "personajes_desvinculados": desvinculados,
            "series_desvinculadas": series_sueltas}


def ruta_retrato(slug: str):
    with get_session() as s:
        if reparto_repo.por_slug(s, slug) is None:
            raise MiembroNoExiste(slug)
    ruta = reparto_repo.ruta_retrato(slug)
    if not ruta.exists():
        raise MiembroNoExiste(slug)
    return ruta


# --- el reparto que propone el hilo -----------------------------------------

def fichar_para_serie(serie_id: int, personajes: list[dict]) -> list[dict]:
    """Da de alta a los protagonistas del hilo y los mete en la serie.

    Es la otra manera de entrar al reparto propio, y la que una serie necesita:
    `promover` da por hecho que ya hay un proyecto con la ficha afinada y una
    cara que convence, y eso vale cuando descubres a alguien escribiendo un
    vídeo. En una serie es al revés — sabes quiénes son antes del primer
    capítulo, y lo que quieres es fijarles la cara y la voz **antes**, para que
    los seis episodios usen la misma.

    No toca una serie que ya tiene reparto fijo: replanificar el hilo no puede
    refichar a nadie ni duplicar a la protagonista. Lo hecho no se toca, igual
    que con los tramos ya rodados.

    No genera ni cara ni voz: eso son GPU y modelo, y van por la cola desde la
    pantalla de la serie (`generar_retrato_reparto` y `crear_su_voz`).
    """
    # El normalizador de claves del casting, que es el que decide cómo se
    # escribe un marcador: tenerlo distinto aquí sería tener {EL VECINO} en una
    # mitad de la app y {EL_VECINO} en la otra.
    from ..services.pipeline.casting import normalizar_tipo

    with get_session() as s:
        if series_repo.miembros(s, serie_id):
            return []
        fichados = []
        for p in personajes:
            ficha = " ".join((p.get("ficha") or "").split())
            nombre = (p.get("nombre") or p.get("clave") or "").strip()
            if not ficha or not nombre:
                # Sin ficha no hay nada que retratar y sin nombre no hay nada
                # que listar: entra el resto, que es mejor que no entrar nadie.
                continue
            clave = personajes_repo.normalizar_clave(p.get("clave") or nombre)
            slug = _slug_libre(s, _slugify(nombre))
            reparto_repo.crear(
                s, slug, nombre, clave, ficha,
                normalizar_tipo(p.get("tipo") or "persona", ficha), 0, "",
            )
            series_repo.anadir_miembro(s, serie_id, slug)
            fichados.append({"slug": slug, "nombre": nombre, "clave": clave})
        s.commit()
    return fichados


def crear_su_voz(slug: str) -> dict:
    """Le escribe una voz desde su ficha y la encola en el banco.

    La instrucción sale de la ficha porque es el mismo material del que sale su
    cara: la edad, el género y el aire que se ven son los que se tienen que oír
    (`voces.instruct_desde_ficha`, los cuatro bloques de VoiceDesign). Queda en
    el banco como cualquier otra voz, así que si no convence se borra y se
    escribe a mano.

    Importado aquí dentro: el banco de voces desvincula las suyas de este
    reparto al borrarlas, y a nivel de módulo el ciclo sería real.
    """
    from ..services import voces as voces_service

    with get_session() as s:
        m = reparto_repo.por_slug(s, slug)
        if m is None:
            raise MiembroNoExiste(slug)
        if not (m.ficha or "").strip():
            raise SinFicha(slug)
        nombre, ficha, tipo = m.nombre, m.ficha, m.tipo or "persona"

    creada = voces_service.crear_para_personaje(
        nombre, voces_service.instruct_desde_ficha(nombre, ficha, tipo)
    )
    with get_session() as s:
        reparto_repo.por_slug(s, slug).voz = creada["slug"]
        s.commit()
    return {"slug": slug, "voz": creada["slug"], "job_id": creada["job_id"]}


def asignar_voz(slug: str, voz_slug: str) -> dict:
    """Le pone una voz que ya está en el banco (o se la quita con "")."""
    with get_session() as s:
        m = reparto_repo.por_slug(s, slug)
        if m is None:
            raise MiembroNoExiste(slug)
        if voz_slug and voces_repo.por_slug(s, voz_slug) is None:
            raise VozNoExiste(voz_slug)
        m.voz = voz_slug
        s.commit()
    return {"slug": slug, "voz": voz_slug}


def encolar_retrato(slug: str, nuevo_seed: bool = False) -> dict:
    """Encola la cara de un miembro del reparto propio.

    Por la cola y no aquí mismo, al contrario que el resto de este módulo:
    promover y traer son copiar un PNG, pero esto es ComfyUI cargando un modelo
    de imagen, y la cola es la que se pelea por la memoria con todo lo demás.
    """
    from ..workers import queue

    with get_session() as s:
        m = reparto_repo.por_slug(s, slug)
        if m is None:
            raise MiembroNoExiste(slug)
        if not (m.ficha or "").strip():
            raise SinFicha(slug)
        miembro_id = m.id
    return {"slug": slug,
            "job_id": queue.encolar("generar_retrato_reparto", miembro_id,
                                    nuevo_seed=nuevo_seed)}
