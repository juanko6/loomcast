"""Series: episodios con continuidad, que es lo que mejor funciona en Shorts.

Una serie es tres cosas y ninguna más: un **nombre**, una **plantilla** y un
**reparto fijo**. Con eso, crear el episodio siguiente es un clic en vez de
repetir a mano todo lo que ya se decidió una vez.

De dónde sale la continuidad:

- **El reparto fijo** se apoya en el reparto propio: la serie guarda a quién hay
  que traer y cada episodio nuevo se los trae con su ficha, su cara y su voz ya
  fijadas (`services/reparto.traer`, que copia el retrato y resuelve la clave
  ocupada numerando). Así nadie vuelve a describir al protagonista en el
  capítulo cuatro.
- **El resumen del episodio anterior** lo escribe el LLM al cerrarlo
  (`pipeline/series.py`) y entra como contexto en el guion del siguiente.

Y una cosa que esta capa **no** hace: tocar el ciclo de vida del proyecto. Cada
episodio produce su vídeo con los mismos estados que cualquier otro, y la serie
no tiene estado propio.

La idea de cada episodio sigue el flujo normal, no uno paralelo: la serie es
dueña de un **tema**, y las ideas de episodio son ideas de ese tema. Eso da dos
caminos con un solo mecanismo —"nuevo episodio" con un apunte de una línea, o
pedirle al LLM ideas de episodio y aprobar una— y los dos acaban en
`ideas.crear_proyecto`, que es donde un proyecto nace en esta app.
"""
from ..db import get_session
from ..repositories import ideas as ideas_repo
from ..repositories import jobs as jobs_repo
from ..repositories import plantillas as plantillas_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import reparto as reparto_repo
from ..repositories import series as series_repo
from ..repositories import temas as temas_repo
from ..services import reparto as reparto_service
# El mismo slug que el de un proyecto: dos reglas distintas para lo mismo solo
# sirven para que un día no casen.
from ..services.ideas import _slugify


class SerieNoExiste(LookupError):
    pass


class PlantillaInvalida(ValueError):
    pass


class MiembroNoExiste(LookupError):
    pass


class MiembroRepetido(ValueError):
    pass


class SlugOcupado(ValueError):
    pass


def _dict(s, serie) -> dict:
    episodios = series_repo.episodios(s, serie.id)
    return {
        "id": serie.id,
        "slug": serie.slug,
        "nombre": serie.nombre,
        "plantilla": serie.plantilla,
        # Tema del que cuelgan las ideas de episodio: con él la UI reutiliza el
        # "pedir más ideas" de siempre.
        "tema_id": serie.tema_id,
        "n_episodios": len(episodios),
        "n_miembros": len(series_repo.miembros(s, serie.id)),
    }


def listar() -> list[dict]:
    with get_session() as s:
        return [_dict(s, x) for x in series_repo.listar(s)]


def _serie(s, serie_id):
    serie = series_repo.obtener(s, serie_id)
    if serie is None:
        raise SerieNoExiste(serie_id)
    return serie


def _episodio_dict(s, p) -> dict:
    idea = ideas_repo.obtener(s, p.idea_id)
    # Importado aquí dentro: el servicio de proyectos llama al de series (el
    # detalle del proyecto dice de qué serie es), así que a nivel de módulo el
    # ciclo sería real.
    from ..services.proyectos import TIPOS_JOB_PROYECTO

    return {
        "proyecto_id": p.id,
        "episodio": p.episodio,
        "titulo": idea.titulo if idea else p.slug,
        "slug": p.slug,
        "estado": p.estado,
        # Si ya está cerrado: es lo que el episodio siguiente va a leer, así que
        # la UI lo marca en el listado y no solo dentro del proyecto.
        "resumen": (p.resumen_episodio or "").strip(),
        "ocupado": bool(
            jobs_repo.activos_de_proyecto(s, p.id, TIPOS_JOB_PROYECTO)
        ),
    }


def detalle(serie_id: int) -> dict:
    with get_session() as s:
        serie = _serie(s, serie_id)
        miembros = []
        for m in series_repo.miembros(s, serie_id):
            fila = reparto_repo.por_slug(s, m.reparto_slug)
            if fila is None:
                # No debería pasar: borrar del reparto propio limpia estas filas
                # (desvincular_reparto). Si pasara, se calla en vez de tirar la
                # vista entera de la serie.
                continue
            miembros.append({
                "slug": fila.slug, "nombre": fila.nombre, "clave": fila.clave,
                "ficha": fila.ficha, "tipo": fila.tipo or "persona",
                "voz": fila.voz or "",
                "retrato": reparto_repo.ruta_retrato(fila.slug).exists(),
            })
        return {
            **_dict(s, serie),
            "miembros": miembros,
            "episodios": [_episodio_dict(s, p)
                          for p in series_repo.episodios(s, serie_id)],
        }


def crear(nombre: str, plantilla: str) -> dict:
    """Crea la serie y el tema del que colgarán sus ideas de episodio."""
    nombre = " ".join(nombre.split())
    if plantilla not in plantillas_repo.listar():
        raise PlantillaInvalida(plantilla)
    with get_session() as s:
        slug = _slugify(nombre)
        if series_repo.por_slug(s, slug):
            raise SlugOcupado(slug)
        tema = temas_repo.crear(s, nombre, plantilla)
        s.flush()
        serie = series_repo.crear(s, slug, nombre, plantilla, tema.id)
        s.commit()
        return _dict(s, serie)


# --- reparto fijo -----------------------------------------------------------

def anadir_miembro(serie_id: int, reparto_slug: str) -> dict:
    """Mete a alguien del reparto propio en el reparto fijo de la serie.

    No se trae a los episodios que ya existen: un capítulo ya escrito no gana
    un personaje por detrás. Entra en los siguientes.
    """
    with get_session() as s:
        _serie(s, serie_id)
        if reparto_repo.por_slug(s, reparto_slug) is None:
            raise MiembroNoExiste(reparto_slug)
        if series_repo.tiene_miembro(s, serie_id, reparto_slug):
            raise MiembroRepetido(reparto_slug)
        series_repo.anadir_miembro(s, serie_id, reparto_slug)
        s.commit()
    return {"slug": reparto_slug}


def quitar_miembro(serie_id: int, reparto_slug: str) -> dict:
    """Lo saca del reparto fijo. Los episodios ya hechos se quedan con él:
    tienen su copia de la ficha y de la cara, y su marcador escrito en los
    prompts."""
    with get_session() as s:
        _serie(s, serie_id)
        if not series_repo.quitar_miembro(s, serie_id, reparto_slug):
            raise MiembroNoExiste(reparto_slug)
        s.commit()
    return {"slug": reparto_slug}


def traer_reparto_fijo(proyecto_id: int) -> list[dict]:
    """Trae al episodio recién creado a todo el reparto fijo de su serie.

    Va fuera de la transacción que crea el proyecto porque `traer` copia un PNG
    y abre su propia sesión. Devuelve con qué clave entró cada uno, que es el
    marcador que acabará en los prompts de escena.

    Lista vacía si el proyecto no es un episodio, que es lo que lo deja ser un
    proyecto normal.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None or p.serie_id is None:
            return []
        slugs = [m.reparto_slug for m in series_repo.miembros(s, p.serie_id)]

    traidos = []
    for slug in slugs:
        try:
            r = reparto_service.traer(slug, proyecto_id)
        except reparto_service.MiembroNoExiste:
            # Carrera con un borrado del reparto propio: el episodio entra sin
            # él, que es mejor que no poder crear el episodio.
            continue
        traidos.append({"slug": slug, **r})
    return traidos


# --- episodios --------------------------------------------------------------

def crear_episodio(serie_id: int, apunte: str = "") -> dict:
    """El camino corto: "nuevo episodio" y ya está escribiéndose el guion.

    `apunte` es opcional y es una línea de dirección ("Ana encuentra la llave").
    Sin él, el episodio lo propone el LLM desde donde quedó el anterior, que es
    para lo que existe el resumen; con él, manda el usuario. En los dos casos el
    episodio nace como cualquier proyecto: de una idea aprobada de un tema.
    """
    apunte = " ".join(apunte.split())
    with get_session() as s:
        serie = _serie(s, serie_id)
        numero = series_repo.siguiente_numero(s, serie_id)
        titulo = f"Episodio {numero}"
        if apunte:
            titulo = f"Episodio {numero}: {apunte[:80]}"
        idea = ideas_repo.crear(
            s, serie.tema_id, titulo=titulo, gancho="",
            # El apunte entra como resumen de la idea porque es el campo que el
            # prompt de guion ya lee; vacío, el guion se apoya solo en la
            # continuidad.
            resumen=apunte,
        )
        s.commit()
        idea_id = idea.id

    # Un solo camino para crear proyectos: el de siempre. Ahí se hereda la serie
    # (el tema es suyo), se numera el episodio y se trae el reparto fijo.
    from ..services import ideas as ideas_service

    creado = ideas_service.crear_proyecto(idea_id)
    return {**creado, "episodio": numero, "idea_id": idea_id}


def borrar(serie_id: int) -> dict:
    """Disuelve la serie: sus episodios se quedan como vídeos sueltos.

    No se borran los episodios (cada uno lleva su guion, su narración y su
    vídeo) ni el tema de las ideas, que sin serie es un tema normal. Lo que se
    va es la serie y su reparto fijo.
    """
    with get_session() as s:
        _serie(s, serie_id)
        sueltos = series_repo.borrar(s, serie_id)
        s.commit()
    return {"episodios_sueltos": sueltos}
