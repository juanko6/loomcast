"""Atajos para sembrar la BD de los tests (siempre vía repositorios)."""
from backend.repositories import escenas as escenas_repo
from backend.repositories import hilos as hilos_repo
from backend.repositories import ideas as ideas_repo
from backend.repositories import personajes as personajes_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import reparto as reparto_repo
from backend.repositories import series as series_repo
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


def serie(s, nombre="La casa de Alicia", plantilla="serie",
          slug="la-casa-de-alicia", premisa="", episodios=0):
    """Una serie con su tema, como la crea el servicio."""
    t = temas_repo.crear(s, nombre, plantilla)
    s.flush()
    x = series_repo.crear(s, slug, nombre, plantilla, t.id)
    x.premisa = premisa
    x.episodios_objetivo = episodios
    s.commit()
    return x


def hilo(s, serie, tramos=3):
    """El hilo de una serie, con un tramo por episodio.

    Sin hilo la serie funciona igual que antes (solo continuidad hacia atrás),
    así que casi todos los tests de series no lo necesitan: se le pone a los que
    comprueban que el episodio sabe qué sitio ocupa.
    """
    h = hilos_repo.crear(s, serie.id, {
        "premisa": "Alicia hereda la casa de su tia y alguien ya vive en ella.",
        "pregunta": "¿Quién entraba en la casa por la noche?",
        "destino": "Alicia descubre que era su hermano y le deja quedarse.",
        "fuera": ["no aparece la policia", "nada sobrenatural"],
        "episodios_recomendados": tramos,
        "por_que": f"el secreto aguanta {tramos} giros",
        "tramos": [
            {"titulo": f"Tramo {i}", "pasa": f"pasa la cosa {i}",
             "cambia": f"cambia la cosa {i}"}
            for i in range(1, tramos + 1)
        ],
    })
    s.commit()
    return h


def episodio(s, serie, numero=1, slug=None, titulo=None, resumen=""):
    """Un proyecto que es episodio `numero` de `serie` (su idea cuelga del tema
    de la serie, como en el flujo real)."""
    i = ideas_repo.crear(s, serie.tema_id, titulo or f"Episodio {numero}", "G", "R")
    s.flush()
    p = proyectos_repo.crear(s, i.id, slug or f"ep-{numero}", serie.plantilla)
    p.serie_id = serie.id
    p.episodio = numero
    p.resumen_episodio = resumen
    s.commit()
    return p


def miembro_reparto(s, slug="ana-narradora", nombre="Ana narradora",
                    clave="ANA", ficha="a tall woman with red hair",
                    tipo="persona", seed=7, voz=""):
    m = reparto_repo.crear(s, slug, nombre, clave, ficha, tipo, seed, voz)
    s.commit()
    return m
