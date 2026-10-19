import pytest

from backend.models import Job
from backend.services.pipeline import musica as musica_pipeline

pytestmark = pytest.mark.integration


@pytest.fixture
def pista(client, dirs_tmp):
    return client.post("/api/musica", json={"idea": "lofi para estudiar"}).json()["id"]


def test_crear_con_valores_por_defecto(client, pista):
    d = client.get(f"/api/musica/{pista}").json()
    assert d["tipo"] == "instrumental" and d["duracion_s"] == 30
    assert (d["bpm"], d["keyscale"], d["timesig"]) == (120, "C major", "4")
    assert d["idioma"] == "en"  # instrumental
    assert d["estado"] == "nueva" and not d["tiene_audio"] and not d["tiene_portada"]


def test_cancion_usa_espanol_por_defecto(client, dirs_tmp):
    i = client.post("/api/musica", json={"tipo": "cancion", "idea": "x"}).json()["id"]
    d = client.get(f"/api/musica/{i}").json()
    assert d["tipo"] == "cancion" and d["idioma"] == "es"


def test_tipo_desconocido_cae_a_instrumental(client, dirs_tmp):
    i = client.post("/api/musica", json={"tipo": "ópera", "idea": "x"}).json()["id"]
    assert client.get(f"/api/musica/{i}").json()["tipo"] == "instrumental"


def test_crear_normaliza_los_campos_musicales(client, dirs_tmp):
    i = client.post("/api/musica", json={
        "tags": "jazz suave y cálido " * 3, "bpm": 9999, "keyscale": "eb MAJOR",
        "timesig": "17", "idioma": " ES ", "duracion_s": 99999}).json()["id"]
    d = client.get(f"/api/musica/{i}").json()
    assert d["bpm"] != 9999 and d["keyscale"] == "Eb major"
    assert d["timesig"] == "4" and d["idioma"] == "es" and d["duracion_s"] == 600


def test_duracion_minima(client, dirs_tmp):
    i = client.post("/api/musica", json={"idea": "x", "duracion_s": -3}).json()["id"]
    assert client.get(f"/api/musica/{i}").json()["duracion_s"] == 5


@pytest.mark.parametrize("cuerpo", [{}, {"idea": "  ", "tags": " "}, {"idea": "", "tags": ""}])
def test_crear_sin_idea_ni_tags_400(client, cuerpo):
    assert client.post("/api/musica", json=cuerpo).status_code == 400


def test_crear_solo_con_tags_vale(client, dirs_tmp):
    assert client.post("/api/musica", json={"tags": "ambient"}).status_code == 200


def test_listar(client, pista):
    assert [(m["id"], m["idea"]) for m in client.get("/api/musica").json()] == [(pista, "lofi para estudiar")]


def test_detalle_inexistente_404(client):
    assert client.get("/api/musica/99").status_code == 404


def test_editar_solo_toca_los_campos_enviados(client, pista):
    client.put(f"/api/musica/{pista}", json={"tags": "nuevo estilo", "bpm": 90})
    d = client.get(f"/api/musica/{pista}").json()
    assert (d["tags"], d["bpm"], d["duracion_s"]) == ("nuevo estilo", 90, 30)
    client.put(f"/api/musica/{pista}", json={"tags": ""})
    assert client.get(f"/api/musica/{pista}").json()["tags"] is None


def test_editar_inexistente_404(client):
    assert client.put("/api/musica/99", json={}).status_code == 404


def test_mejorar_encola(client, pista, jobs_encolados):
    assert client.post(f"/api/musica/{pista}/mejorar").status_code == 200
    assert jobs_encolados == [("mejorar_prompt_musica", pista)]
    assert client.post("/api/musica/99/mejorar").status_code == 404


def test_generar_guarda_los_campos_y_el_seed_antes_de_encolar(client, pista, jobs_encolados):
    r = client.post(f"/api/musica/{pista}/generar", json={"tags": "rock", "seed": 7, "bpm": 150})
    assert r.status_code == 200 and jobs_encolados == [("generar_musica", pista)]
    d = client.get(f"/api/musica/{pista}").json()
    assert (d["tags"], d["seed"], d["bpm"]) == ("rock", 7, 150)


def test_generar_sin_cuerpo_resetea_el_seed(client, pista, jobs_encolados):
    client.post(f"/api/musica/{pista}/generar", json={"seed": 7})
    client.post(f"/api/musica/{pista}/generar")
    assert client.get(f"/api/musica/{pista}").json()["seed"] is None


def test_generar_inexistente_404(client, jobs_encolados):
    assert client.post("/api/musica/99/generar").status_code == 404
    assert jobs_encolados == []


def test_detalle_marca_ocupado_solo_con_jobs_de_musica(client, session, pista):
    session.add(Job(tipo="generar_voz", ref_id=pista, estado="corriendo"))
    session.commit()
    assert client.get(f"/api/musica/{pista}").json()["ocupado"] is False
    session.add(Job(tipo="generar_musica", ref_id=pista, estado="pendiente"))
    session.commit()
    assert client.get(f"/api/musica/{pista}").json()["ocupado"] is True


def test_borrar_quita_fila_y_carpeta(client, pista, dirs_tmp):
    car = musica_pipeline.carpeta(pista)
    car.mkdir(parents=True)
    (car / "musica.flac").write_bytes(b"x")
    assert client.delete(f"/api/musica/{pista}").json() == {
        "borrada": pista, "archivos": 1, "proyectos_desvinculados": 0}
    assert not car.exists()
    assert client.delete(f"/api/musica/{pista}").status_code == 404


def test_audio_y_portada_404_hasta_que_existen(client, pista, dirs_tmp):
    assert client.get(f"/api/musica/{pista}/audio").status_code == 404
    assert client.get(f"/api/musica/{pista}/portada").status_code == 404
    car = musica_pipeline.carpeta(pista)
    car.mkdir(parents=True)
    (car / "musica.mp3").write_bytes(b"mp3")
    (car / "portada.png").write_bytes(b"png")
    r = client.get(f"/api/musica/{pista}/audio")
    assert r.content == b"mp3" and r.headers["content-type"] == "audio/mpeg"
    assert client.get(f"/api/musica/{pista}/portada").headers["content-type"] == "image/png"
    assert client.get(f"/api/musica/{pista}").json()["tiene_audio"] is True


def test_audio_flac_con_su_mime(client, pista, dirs_tmp):
    car = musica_pipeline.carpeta(pista)
    car.mkdir(parents=True)
    (car / "musica.flac").write_bytes(b"f")
    assert client.get(f"/api/musica/{pista}/audio").headers["content-type"] == "audio/flac"
