import pytest

from backend.repositories import albumes as albumes_repo
from backend.schemas import AlbumPlanLLM, MusicaPromptLLM
from backend.services.pipeline import album as album_pipe
from backend.workers import queue
from tests.integration.test_album import BRIEF, _plan

pytestmark = pytest.mark.integration


@pytest.fixture
def album(client, dirs_tmp, fake_llm, jobs_encolados):
    """Un álbum de 3 pistas ya planificado y escrito, en revisión."""
    aid = client.post("/api/albumes", json={"idea": "jazz noir", "num_pistas": 3}).json()["id"]
    fake_llm.responder(AlbumPlanLLM, _plan(3))
    fake_llm.responder(MusicaPromptLLM, BRIEF)
    album_pipe.planificar_album(aid)
    album_pipe.escribir_album(aid)
    jobs_encolados.clear()
    return aid


def test_crear_desde_idea_encola_el_plan(client, jobs_encolados):
    r = client.post("/api/albumes", json={"idea": "lofi de lluvia", "num_pistas": 99})
    aid = r.json()["id"]
    assert jobs_encolados == [("planificar_album", aid)]
    assert client.get(f"/api/albumes/{aid}").json()["num_pistas"] == 20


def test_crear_sin_idea_400(client):
    assert client.post("/api/albumes", json={"idea": "  "}).status_code == 400


def test_crear_desde_pista_hereda_su_semilla(client, jobs_encolados):
    mid = client.post("/api/musica", json={"tags": "noir jazz with sax " * 3}).json()["id"]
    client.post(f"/api/musica/{mid}/generar", json={"seed": 31337})
    aid = client.post("/api/albumes", json={"musica_id": mid, "num_pistas": 4}).json()["id"]
    d = client.get(f"/api/albumes/{aid}").json()
    assert d["seed"] == 31337 and d["origen_musica_id"] == mid


def test_crear_desde_cancion_400(client):
    mid = client.post("/api/musica", json={"tipo": "cancion", "tags": "pop " * 10}).json()["id"]
    assert client.post("/api/albumes", json={"musica_id": mid}).status_code == 400


def test_detalle_trae_pistas_con_duracion_y_compases(client, album):
    d = client.get(f"/api/albumes/{album}").json()
    assert d["estado"] == "revision" and len(d["pistas"]) == 3
    p = d["pistas"][0]
    assert p["compases"] == 24 and p["escrita"] and p["titulo"] == "Tema 1"
    assert d["duracion_total_s"] == sum(x["duracion_s"] for x in d["pistas"])


def test_cambiar_el_tempo_recalcula_la_duracion(client, album):
    p = client.get(f"/api/albumes/{album}").json()["pistas"][0]
    client.put(f"/api/albumes/{album}/pistas/{p['id']}", json={"bpm": 60, "intencion": "otra"})
    q = client.get(f"/api/albumes/{album}").json()["pistas"][0]
    assert q["duracion_s"] == 24 * 4 + 4 and q["intencion"] == "otra"


def test_producir_encola_todas_con_la_semilla_y_la_portada_al_final(client, album, jobs_encolados):
    ids = [p["id"] for p in client.get(f"/api/albumes/{album}").json()["pistas"]]
    r = client.post(f"/api/albumes/{album}/producir").json()
    assert r["pistas"] == 3
    assert jobs_encolados == [("generar_musica", i) for i in ids] + [("generar_portada_album", album)]
    d = client.get(f"/api/albumes/{album}").json()
    assert d["estado"] == "produciendo" and {p["seed"] for p in d["pistas"]} == {d["seed"]}


def test_producir_con_pistas_sin_escribir_400(client, dirs_tmp, fake_llm, jobs_encolados):
    aid = client.post("/api/albumes", json={"idea": "x", "num_pistas": 2}).json()["id"]
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(aid)
    r = client.post(f"/api/albumes/{aid}/producir")
    assert r.status_code == 400 and "1, 2" in r.json()["detail"]


def test_quitar_y_ordenar(client, album):
    ids = [p["id"] for p in client.get(f"/api/albumes/{album}").json()["pistas"]]
    client.delete(f"/api/albumes/{album}/pistas/{ids[0]}")
    assert [p["pista_n"] for p in client.get(f"/api/albumes/{album}").json()["pistas"]] == [1, 2]
    client.put(f"/api/albumes/{album}/orden", json={"ids": [ids[2], ids[1]]})
    assert [p["id"] for p in client.get(f"/api/albumes/{album}").json()["pistas"]] == [ids[2], ids[1]]
    assert client.put(f"/api/albumes/{album}/orden", json={"ids": [ids[2]]}).status_code == 400


def test_cambiar_la_firma_la_cambia_en_cada_brief(client, album):
    client.put(f"/api/albumes/{album}", json={"firma": "Recorded to tape, bright and wide."})
    d = client.get(f"/api/albumes/{album}").json()
    assert all(p["tags"].endswith("Recorded to tape, bright and wide.") for p in d["pistas"])


def test_borrar_el_album_borra_sus_pistas(client, album, session):
    client.delete(f"/api/albumes/{album}")
    assert client.get(f"/api/albumes/{album}").status_code == 404
    assert client.get("/api/musica").json() == []


def test_una_pista_de_album_no_encadena_portada_propia(client, album):
    p = client.get(f"/api/albumes/{album}").json()["pistas"][0]
    assert queue._encadenado("generar_musica", p["id"]) is None
    suelta = client.post("/api/musica", json={"tags": "ambient " * 5}).json()["id"]
    assert queue._encadenado("generar_musica", suelta) == "generar_portada_musica"
