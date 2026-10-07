import pytest

from backend.models import Job

pytestmark = pytest.mark.integration


def test_job_inexistente_404(client):
    assert client.get("/api/jobs/123").status_code == 404


def test_ver_job_y_listado_de_activos(client, session):
    j = Job(tipo="generar_ideas", ref_id=1, estado="pendiente")
    session.add(j)
    session.commit()

    r = client.get(f"/api/jobs/{j.id}")
    assert r.status_code == 200
    assert r.json()["estado"] == "pendiente"
    assert r.json()["progreso"] is None

    assert [x["id"] for x in client.get("/api/jobs").json()] == [j.id]
