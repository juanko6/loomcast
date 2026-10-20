"""Atajos para sembrar la BD de los tests (siempre vía repositorios)."""
from backend.repositories import escenas as escenas_repo
from backend.repositories import ideas as ideas_repo
from backend.repositories import personajes as personajes_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import reparto as reparto_repo
from backend.repositories import temas as temas_repo


def tema(s, texto="el espacio", plantilla="curiosidades"):
    t = temas_repo.crear(s, texto, plantilla)
    s.commit()
    return t


def idea(s, tema_id, titulo="Una idea", gancho="Gancho", resumen="Resumen"):
    i = ideas_repo.crear(s, tema_id, titulo, gancho, resumen)
    s.commit()
    return i


def proyecto(s, slug="demo", plantilla="curiosidades", titulo="Una idea"):
    t = tema(s, plantilla=plantilla)
    i = idea(s, t.id, titulo=titulo)
    p = proyectos_repo.crear(s, i.id, slug, plantilla)
    s.commit()
    return p


def escenas(s, proyecto_id, n=2):
    escenas_repo.reemplazar_todas(s, proyecto_id, [
        {"orden": k, "t_inicio": k * 4.0, "t_fin": (k + 1) * 4.0,
         "texto": f"texto {k}", "prompt": f"prompt visual de la escena {k} " * 2}
        for k in range(1, n + 1)
    ])
    s.commit()


def personaje(s, proyecto_id, clave="ANA", nombre="Ana",
              ficha="a tall woman with red hair", tipo="persona",
              reparto_slug="", voz=""):
    personajes_repo.crear(s, proyecto_id, clave, nombre, ficha, 1, tipo,
                          reparto_slug=reparto_slug, voz=voz)
    s.commit()


def miembro_reparto(s, slug="ana-narradora", nombre="Ana narradora",
                    clave="ANA", ficha="a tall woman with red hair",
                    tipo="persona", seed=7, voz=""):
    m = reparto_repo.crear(s, slug, nombre, clave, ficha, tipo, seed, voz)
    s.commit()
    return m
