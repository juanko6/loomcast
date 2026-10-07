import pytest

from backend.repositories import ideas as ideas_repo
from backend.repositories import proyectos as proyectos_repo
from tests import factories as f

pytestmark = pytest.mark.integration


def test_cambiar_estado_de_idea(client, session):
    i = f.idea(session, f.tema(session).id)
    r = client.post(f"/api/ideas/{i.id}/estado", json={"estado": "descartada"})
    assert r.status_code == 200
    session.expire_all()
    assert ideas_repo.obtener(session, i.id).estado == "descartada"


@pytest.mark.parametrize("estado", ["", "APROBADA", "otra", "propuesta "])
def test_estado_invalido_es_400(client, session, estado):
    i = f.idea(session, f.tema(session).id)
    assert client.post(f"/api/ideas/{i.id}/estado", json={"estado": estado}).status_code == 400


def test_estado_de_idea_inexistente_es_404(client):
    assert client.post("/api/ideas/99/estado", json={"estado": "aprobada"}).status_code == 404


def test_estado_sin_cuerpo_es_422(client):
    assert client.post("/api/ideas/1/estado", json={}).status_code == 422


def test_crear_proyecto_aprueba_la_idea_y_encola_el_guion(client, session, jobs_encolados):
    i = f.idea(session, f.tema(session).id, titulo="¡Qué Pasó en Júpiter!")

    r = client.post(f"/api/ideas/{i.id}/proyecto")

    body = r.json()
    assert r.status_code == 200 and "job_id" in body
    assert jobs_encolados == [("generar_guion", body["proyecto_id"])]
    session.expire_all()
    p = proyectos_repo.obtener(session, body["proyecto_id"])
    assert p.slug == "que-paso-en-jupiter" and p.plantilla == "curiosidades"
    assert ideas_repo.obtener(session, i.id).estado == "aprobada"


def test_crear_proyecto_dos_veces_no_duplica(client, session, jobs_encolados):
    i = f.idea(session, f.tema(session).id)
    primero = client.post(f"/api/ideas/{i.id}/proyecto").json()
    segundo = client.post(f"/api/ideas/{i.id}/proyecto").json()
    assert segundo == {"proyecto_id": primero["proyecto_id"], "ya_existia": True}
    assert len(jobs_encolados) == 1


def test_slug_se_desambigua_si_el_titulo_se_repite(client, session):
    t = f.tema(session)
    a = f.idea(session, t.id, titulo="Mismo título")
    b = f.idea(session, t.id, titulo="Mismo título")
    client.post(f"/api/ideas/{a.id}/proyecto")
    pid = client.post(f"/api/ideas/{b.id}/proyecto").json()["proyecto_id"]
    session.expire_all()
    assert proyectos_repo.obtener(session, pid).slug == "mismo-titulo-2"


def test_titulo_sin_caracteres_validos_cae_a_slug_generico(client, session):
    i = f.idea(session, f.tema(session).id, titulo="¿¡?!")
    pid = client.post(f"/api/ideas/{i.id}/proyecto").json()["proyecto_id"]
    session.expire_all()
    assert proyectos_repo.obtener(session, pid).slug == "proyecto"


def test_crear_proyecto_de_idea_inexistente_es_404(client):
    assert client.post("/api/ideas/99/proyecto").status_code == 404
