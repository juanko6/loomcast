import itertools
import re

from sqlalchemy.orm import Session

from ..models import Personaje

# El token va entre llaves en el prompt ({ANA}), así que la clave solo puede
# llevar letras, dígitos y guion bajo: cualquier otra cosa rompería el marcador.
_LIMPIA = re.compile(r"[^A-Z0-9_]")


def normalizar_clave(clave: str) -> str:
    """A mayúsculas y sin caracteres que puedan romper el marcador {CLAVE}."""
    limpia = _LIMPIA.sub("", clave.strip().upper().replace(" ", "_"))
    # "el escritor  raro" no debe quedar en ESCRITOR__RARO.
    return re.sub(r"_+", "_", limpia).strip("_")


def reemplazar_todos(s: Session, proyecto_id: int,
                     personajes: list[dict]) -> list[Personaje]:
    """Regenerar el casting reemplaza el reparto del proyecto, igual que hacen
    las escenas: son dos vistas del mismo guion.

    **Con una excepción: los traídos del reparto propio sobreviven.** Perderlos
    sería lo peor de las dos opciones posibles: el usuario los eligió a mano,
    su retrato ya está copiado en la carpeta del proyecto y su marcador puede
    estar escrito en los prompts de escena, así que un "regenerar reparto" los
    borraría sin avisar y dejaría esos prompts nombrando a nadie. Conservarlos
    no es a ciegas: si el LLM acaba de escribir a alguien con la misma clave,
    manda el del reparto y el del LLM se descarta, porque tener una ficha
    canónica que no deriva entre vídeos es justo para lo que se guardó.

    Devuelve el reparto resultante en orden: primero los conservados.
    """
    conservados = [p for p in por_proyecto(s, proyecto_id) if p.reparto_slug]
    (
        s.query(Personaje)
        .filter(Personaje.proyecto_id == proyecto_id, Personaje.reparto_slug == "")
        .delete()
    )
    for i, p in enumerate(conservados):
        p.orden = i

    ocupadas = {p.clave for p in conservados}
    filas = []
    for datos in personajes:
        if datos["clave"] in ocupadas:
            continue
        ocupadas.add(datos["clave"])
        filas.append(Personaje(
            proyecto_id=proyecto_id,
            **{**datos, "orden": len(conservados) + len(filas)},
        ))
    s.add_all(filas)
    return conservados + filas


def clave_libre(s: Session, proyecto_id: int, clave: str) -> str:
    """`clave` si nadie la usa en el proyecto, y si no ANA_2, ANA_3…

    Las claves son marcadores `{CLAVE}` ya escritos en los prompts de escena:
    traer del reparto propio a alguien cuya clave coincide con la de otro no
    puede pisarlo ni dejar dos con el mismo marcador, porque la sustitución se
    hace por texto y el segundo se quedaría con la ficha del primero.
    """
    ocupadas = {p.clave for p in por_proyecto(s, proyecto_id)}
    if clave not in ocupadas:
        return clave
    return next(
        c for c in (f"{clave}_{n}" for n in itertools.count(2)) if c not in ocupadas
    )


def crear(s: Session, proyecto_id: int, clave: str, nombre: str,
          ficha: str, seed: int, tipo: str = "persona",
          reparto_slug: str = "") -> Personaje:
    """Añade un personaje al reparto, detrás de los que ya hay."""
    orden = 1 + max((p.orden for p in por_proyecto(s, proyecto_id)), default=-1)
    fila = Personaje(proyecto_id=proyecto_id, orden=orden, clave=clave,
                     nombre=nombre, ficha=ficha, seed=seed, tipo=tipo,
                     reparto_slug=reparto_slug)
    s.add(fila)
    return fila


def borrar(s: Session, proyecto_id: int, clave: str) -> int:
    return (
        s.query(Personaje)
        .filter(Personaje.proyecto_id == proyecto_id, Personaje.clave == clave)
        .delete()
    )


def existe(s: Session, proyecto_id: int, clave: str) -> bool:
    return any(p.clave == clave for p in por_proyecto(s, proyecto_id))


def por_proyecto(s: Session, proyecto_id: int) -> list[Personaje]:
    return (
        s.query(Personaje)
        .filter(Personaje.proyecto_id == proyecto_id)
        .order_by(Personaje.orden)
        .all()
    )


def fichas(s: Session, proyecto_id: int) -> dict[str, str]:
    """Casting como {CLAVE: ficha}, que es como lo consume la sustitución."""
    return {p.clave: p.ficha for p in por_proyecto(s, proyecto_id) if p.ficha}


def actualizar(s: Session, proyecto_id: int, cambios: dict[str, dict]) -> int:
    """Edita nombre y/o ficha de los personajes indicados, por clave.

    El tipo (persona | objeto) no se toca aquí: lo decide el casting a partir de
    lo que diga el LLM y de la propia ficha. Editar la ficha sí lo revisa, por
    si pasa a describir algo sin cara.
    """
    from ..services.pipeline.casting import normalizar_tipo

    n = 0
    for p in por_proyecto(s, proyecto_id):
        campos = cambios.get(p.clave)
        if campos is None:
            continue
        if "nombre" in campos:
            p.nombre = campos["nombre"]
        if "ficha" in campos:
            p.ficha = campos["ficha"]
            p.tipo = normalizar_tipo(p.tipo, p.ficha)
        n += 1
    return n
