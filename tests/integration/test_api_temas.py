import pytest

pytestmark = pytest.mark.integration


def test_crear_y_listar_tema(client, jobs_encolados):
    r = client.post("/api/temas", json={"texto": "  el espacio ", "plantilla": "curiosidades"})
    assert r.status_code == 200
    assert jobs_encolados == [("generar_ideas", r.json()["tema_id"])]

    temas = client.get("/api/temas").json()
    assert [(t["texto"], t["plantilla"], t["n_ideas"]) for t in temas] == [
        ("el espacio", "curiosidades", 0)
    ]


def test_plantilla_desconocida_es_400(client):
    r = client.post("/api/temas", json={"texto": "x", "plantilla": "no_existe"})
    assert r.status_code == 400


def test_mas_ideas_de_tema_inexistente_es_404(client):
    assert client.post("/api/temas/999/ideas").status_code == 404


def test_ideas_de_tema_marcan_cuales_ya_son_proyecto(client, session):
    from tests import factories as f

    t = f.tema(session)
    a, b = f.idea(session, t.id, titulo="A"), f.idea(session, t.id, titulo="B")
    pid = client.post(f"/api/ideas/{a.id}/proyecto").json()["proyecto_id"]

    ideas = client.get(f"/api/temas/{t.id}/ideas").json()

    assert [(i["titulo"], i["proyecto_id"]) for i in ideas] == [("A", pid), ("B", None)]
    assert ideas[0]["estado"] == "aprobada" and ideas[1]["estado"] == "propuesta"


def test_ideas_de_tema_sin_ideas(client, session):
    from tests import factories as f

    assert client.get(f"/api/temas/{f.tema(session).id}/ideas").json() == []


def test_mas_ideas_encola_la_generacion(client, session, jobs_encolados):
    from tests import factories as f

    t = f.tema(session)
    assert client.post(f"/api/temas/{t.id}/ideas").status_code == 200
    assert jobs_encolados == [("generar_ideas", t.id)]


def test_borrar_tema_con_sus_ideas(client, session):
    from backend.models import Idea
    from tests import factories as f

    t = f.tema(session)
    f.idea(session, t.id)
    f.idea(session, t.id)

    assert client.delete(f"/api/temas/{t.id}").json() == {"ideas": 2}
    assert client.get("/api/temas").json() == []
    assert session.query(Idea).count() == 0


def test_borrar_tema_inexistente_404(client):
    assert client.delete("/api/temas/99").status_code == 404


def test_borrar_tema_con_proyectos_409_y_no_borra_nada(client, session):
    from tests import factories as f

    t = f.tema(session)
    i = f.idea(session, t.id, titulo="Ya es proyecto")
    f.idea(session, t.id, titulo="Libre")
    client.post(f"/api/ideas/{i.id}/proyecto")

    r = client.delete(f"/api/temas/{t.id}")

    assert r.status_code == 409 and "Ya es proyecto" in r.json()["detail"]
    assert len(client.get(f"/api/temas/{t.id}/ideas").json()) == 2


def test_crear_tema_sin_texto_422_y_con_texto_vacio_se_guarda_recortado(client):
    assert client.post("/api/temas", json={"plantilla": "drama"}).status_code == 422
