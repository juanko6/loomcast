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
