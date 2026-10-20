"""Continuidad de una serie: el contexto del guion y el resumen del episodio.

Dos piezas, y las dos son texto:

- `contexto_continuidad` es lo que se le añade al LLM al escribir el guion de un
  episodio: quién es el reparto fijo (con las claves con las que ya está en el
  proyecto, porque son los marcadores que el casting y las escenas usarán) y qué
  pasó en el episodio anterior. **Para un proyecto suelto devuelve cadena
  vacía**, y entonces la petición del guion es byte a byte la de siempre.

- `generar_resumen_episodio` es la otra mitad: al cerrar un episodio, el LLM
  escribe en qué quedó, y eso es lo que leerá el siguiente. Se guarda en el
  proyecto y es editable como el guion o los metadatos: una serie que depende de
  un resumen que nadie puede corregir deriva en tres capítulos.

El resumen **no toca el estado del proyecto**: `avanzar_estado` describe la
producción de un vídeo (IDEA → … → FINAL) y cerrar el episodio no es una etapa
más de ese vídeo, es lo que le pasa a la serie cuando ese vídeo ya está.
"""
import json

from ...clients import llm
from ...config import PROMPTS_DIR
from ...db import get_session
from ...repositories import guiones as guiones_repo
from ...repositories import ideas as ideas_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import personajes as personajes_repo
from ...repositories import proyectos as proyectos_repo
from ...repositories import series as series_repo
from ...schemas import ResumenEpisodioLLM


def _titulo(s, proyecto) -> str:
    """Cómo se llama el episodio: su título de publicación si ya lo tiene, y si
    no el de la idea con la que nació."""
    meta = metadatos_repo.ultimo(s, proyecto.id)
    if meta:
        titulo = json.loads(meta.contenido)["youtube"]["titulo"]
        if titulo:
            return titulo
    idea = ideas_repo.obtener(s, proyecto.idea_id)
    return idea.titulo if idea else proyecto.slug


def contexto_continuidad(proyecto_id: int) -> str:
    """Lo que el guion de este episodio tiene que saber de los anteriores.

    Cadena vacía si el proyecto no es un episodio: es lo que mantiene intacta la
    etapa de guion de los vídeos sueltos.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None or p.serie_id is None:
            return ""
        serie = series_repo.obtener(s, p.serie_id)
        if serie is None:
            return ""
        # El reparto se lee del proyecto y no de la serie: aquí hacen falta las
        # claves con las que entraron de verdad, que pueden no ser las que
        # propone el reparto propio si alguna estaba ocupada ({ANA_2}).
        fijos = [
            f"- {{{x.clave}}} {x.nombre or x.clave}"
            + (f": {x.ficha}" if x.ficha else "")
            for x in personajes_repo.por_proyecto(s, proyecto_id)
            if x.reparto_slug
        ]
        previo = series_repo.anterior(s, p.serie_id, p.episodio)
        resumen_previo, numero_previo, titulo_previo = "", 0, ""
        if previo is not None:
            resumen_previo = (previo.resumen_episodio or "").strip()
            numero_previo = previo.episodio
            titulo_previo = _titulo(s, previo)
        nombre, numero = serie.nombre, p.episodio

    partes = [f"CONTINUIDAD DE LA SERIE «{nombre}» — episodio {numero}"]
    if fijos:
        partes.append(
            "Reparto fijo de la serie. Son los mismos de siempre y el "
            "espectador ya los conoce: no los vuelvas a presentar, y cuando "
            "hablen atribuye la línea con su clave tal cual está escrita aquí.\n"
            + "\n".join(fijos)
        )
    if resumen_previo:
        partes.append(
            f"En el episodio anterior ({numero_previo}"
            f"{f' — «{titulo_previo}»' if titulo_previo else ''}) pasó esto:\n"
            f"{resumen_previo}\n\n"
            "Este episodio continúa desde ahí: recoge lo que quedó abierto sin "
            "resumir el anterior (quien llega nuevo tiene que entenderlo igual, "
            "con una frase, no con un repaso)."
        )
    elif numero > 1:
        partes.append(
            "No hay resumen del episodio anterior, así que no te inventes lo "
            "que pasó: cuenta algo que funcione por sí solo con este reparto."
        )
    else:
        partes.append(
            "Es el primer episodio: planta la situación y deja algo abierto "
            "para el siguiente."
        )
    return "\n\n".join(partes)


def resumen_pendiente(proyecto_id: int) -> bool:
    """Si es un episodio al que todavía le falta su resumen.

    La cola lo consulta al terminar el armado para escribirlo sola: es el
    momento en que el episodio está de verdad cerrado, y así el siguiente ya
    nace con continuidad sin que haya que acordarse de pedirla.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        return (
            p is not None
            and p.serie_id is not None
            and not (p.resumen_episodio or "").strip()
        )


def generar_resumen_episodio(proyecto_id: int) -> str:
    """Escribe en qué quedó este episodio, para el guion del siguiente."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        if p.serie_id is None:
            raise ValueError(
                "Este proyecto no es un episodio de ninguna serie: el resumen "
                "solo sirve para dar continuidad al episodio siguiente."
            )
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El episodio no tiene guion todavía")
        serie = series_repo.obtener(s, p.serie_id)
        nombre = serie.nombre if serie else ""
        numero, titulo = p.episodio, _titulo(s, p)
        previo = series_repo.anterior(s, p.serie_id, numero)
        # El resumen anterior entra también: así el que se escribe ahora
        # arrastra los hilos que siguen abiertos desde antes en vez de contar
        # solo este capítulo y perder la mitad de la historia en el camino.
        antes = (previo.resumen_episodio or "").strip() if previo else ""

    guion_texto = guiones_repo.texto_narrado(json.loads(guion_row.contenido))
    user = (
        f"Serie: «{nombre}»\n"
        f"Episodio {numero}: {titulo}\n\n"
        + (f"Resumen del episodio anterior:\n{antes}\n\n" if antes else "")
        + f"Guion narrado de este episodio:\n```\n{guion_texto}\n```"
    )
    sistema = (PROMPTS_DIR / "resumen_episodio.md").read_text()
    r = llm.chat(sistema, user, ResumenEpisodioLLM)

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        p.resumen_episodio = r.resumen.strip()
        s.commit()
    return f"Resumen del episodio {numero} escrito ({len(r.resumen)} caracteres)"
