"""Lógica de negocio de temas e ideas propuestas."""
from ..db import get_session
from ..repositories import ideas as ideas_repo
from ..repositories import plantillas as plantillas_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import series as series_repo
from ..repositories import temas as temas_repo
from ..workers import queue


class TemaNoExiste(LookupError):
    pass


class PlantillaInvalida(ValueError):
    pass


def crear_tema(texto: str, plantilla: str) -> dict:
    if plantilla not in plantillas_repo.listar():
        raise PlantillaInvalida(plantilla)
    with get_session() as s:
        tema = temas_repo.crear(s, texto.strip(), plantilla)
        s.commit()
        tema_id = tema.id
    job_id = queue.encolar("generar_ideas", tema_id)
    return {"tema_id": tema_id, "job_id": job_id}


def listar_temas() -> list[dict]:
    with get_session() as s:
        out = []
        for t in temas_repo.listar(s):
            ideas = ideas_repo.por_tema(s, t.id)
            serie = series_repo.por_tema(s, t.id)
            out.append({
                "id": t.id,
                "texto": t.texto,
                "plantilla": t.plantilla,
                "n_ideas": len(ideas),
                "n_aprobadas": sum(1 for i in ideas if i.estado == "aprobada"),
                # El tema de una serie no es un tema que el usuario haya creado:
                # es de donde cuelgan sus ideas de episodio, y se entra a él
                # desde la serie. La UI no lo lista aparte para no enseñar la
                # misma cosa dos veces con el mismo nombre.
                "serie": serie.nombre if serie else None,
            })
        return out


def ideas_de_tema(tema_id: int) -> list[dict]:
    with get_session() as s:
        con_proyecto = {
            p.idea_id: p.id for p in proyectos_repo.listar(s)
        }
        return [
            {
                "id": i.id, "titulo": i.titulo, "gancho": i.gancho,
                "resumen": i.resumen, "estado": i.estado,
                "proyecto_id": con_proyecto.get(i.id),
            }
            for i in ideas_repo.por_tema(s, tema_id)
        ]


def pedir_mas_ideas(tema_id: int) -> int:
    with get_session() as s:
        if temas_repo.obtener(s, tema_id) is None:
            raise TemaNoExiste(tema_id)
    return queue.encolar("generar_ideas", tema_id)


class TemaConProyectos(RuntimeError):
    """El tema tiene ideas que ya se convirtieron en proyectos."""

    def __init__(self, titulos: list[str]):
        self.titulos = titulos
        super().__init__(", ".join(titulos))


def borrar_tema(tema_id: int) -> dict:
    """Borra el tema y sus ideas.

    Se niega si alguna idea ya tiene proyecto: esos proyectos llevan guion, voz
    y video, y borrarlos de rebote por eliminar el tema sería una pérdida
    desproporcionada. Hay que borrarlos antes, uno a uno y a conciencia.
    """
    with get_session() as s:
        tema = temas_repo.obtener(s, tema_id)
        if tema is None:
            raise TemaNoExiste(tema_id)
        ideas = ideas_repo.por_tema(s, tema_id)
        con_proyecto = [
            i.titulo for i in ideas if proyectos_repo.por_idea(s, i.id) is not None
        ]
        if con_proyecto:
            raise TemaConProyectos(con_proyecto)
        n = len(ideas)
        temas_repo.borrar(s, tema_id)
        s.commit()
    return {"ideas": n}
