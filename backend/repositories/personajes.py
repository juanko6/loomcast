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
    """Regenerar el casting reemplaza el reparto completo del proyecto, igual
    que hacen las escenas: son dos vistas del mismo guion."""
    s.query(Personaje).filter(Personaje.proyecto_id == proyecto_id).delete()
    filas = [Personaje(proyecto_id=proyecto_id, **p) for p in personajes]
    s.add_all(filas)
    return filas


def crear(s: Session, proyecto_id: int, clave: str, nombre: str,
          ficha: str, seed: int, tipo: str = "persona") -> Personaje:
    """Añade un personaje al reparto, detrás de los que ya hay."""
    orden = 1 + max((p.orden for p in por_proyecto(s, proyecto_id)), default=-1)
    fila = Personaje(proyecto_id=proyecto_id, orden=orden, clave=clave,
                     nombre=nombre, ficha=ficha, seed=seed, tipo=tipo)
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
