import io

import pytest
from PIL import Image

from backend.models import Job
from backend.repositories import galeria as galeria_repo
from backend.services.pipeline import imagen_libre

pytestmark = pytest.mark.integration


def _png(modo="RGB", tam=(10, 10), formato="PNG") -> bytes:
    b = io.BytesIO()
    Image.new(modo, tam, (200, 10, 10)).save(b, formato)
    return b.getvalue()


@pytest.fixture
def img(client, dirs_tmp):
    return client.post("/api/galeria", json={"idea": "un gato"}).json()["id"]


# --- motores ----------------------------------------------------------------

def test_motores_filtra_por_modo_y_marca_el_defecto(client):
    todos = {m["id"]: m for m in client.get("/api/galeria/motores").json()}
    generar = {m["id"] for m in client.get("/api/galeria/motores?modo=generar").json()}
    editar = {m["id"] for m in client.get("/api/galeria/motores?modo=editar").json()}
    assert {"zimage", "qwen", "flux2klein"} <= set(todos)
    assert "qwen" not in generar and "qwen" in editar and "flux2klein" in generar & editar
    assert "generar" in todos["zimage"]["defecto_en"]


def test_motores_con_modo_desconocido_devuelve_vacio(client):
    assert client.get("/api/galeria/motores?modo=raro").json() == []


# --- crear ------------------------------------------------------------------

def test_crear_generar_redondea_el_tamano_a_multiplos_de_64(client, img):
    d = client.get(f"/api/galeria/{img}").json()
    assert (d["width"], d["height"]) == (768, 1344) and d["motor"] == "zimage"
    assert d["estado"] == "nueva" and d["seeds"] == [] and d["ocupado"] is False


@pytest.mark.parametrize("pedido,esperado", [
    (1, 256), (100000, 1536), (1000, 1024), (-5, 256)])
def test_crear_generar_acota_el_lado(client, dirs_tmp, pedido, esperado):
    i = client.post("/api/galeria", json={"idea": "x", "width": pedido, "height": pedido}).json()["id"]
    d = client.get(f"/api/galeria/{i}").json()
    assert (d["width"], d["height"]) == (esperado, esperado)


@pytest.mark.parametrize("idea", ["", "   ", "\n"])
def test_crear_generar_con_idea_vacia_400(client, idea):
    assert client.post("/api/galeria", json={"idea": idea}).status_code == 400


def test_crear_generar_con_motor_que_no_sabe_generar_400(client):
    r = client.post("/api/galeria", json={"idea": "x", "motor": "qwen"})
    assert r.status_code == 400 and "generar" in r.json()["detail"]
    assert client.post("/api/galeria", json={"idea": "x", "motor": "no_existe"}).status_code == 400


def test_crear_generar_sin_idea_422(client):
    assert client.post("/api/galeria", json={}).status_code == 422


def test_crear_editar_normaliza_la_imagen_a_png_rgb(client, dirs_tmp):
    r = client.post("/api/galeria/editar", data={"idea": "ponle gafas"},
                    files={"imagen": ("a.jpg", _png(formato="JPEG"), "image/jpeg")})
    assert r.status_code == 200
    fuente = imagen_libre.ruta_fuente(r.json()["id"])
    with Image.open(fuente) as im:
        assert im.format == "PNG" and im.mode == "RGB"
    assert client.get(f"/api/galeria/{r.json()['id']}/fuente").status_code == 200


def test_crear_editar_con_rgba_se_aplana_a_rgb(client, dirs_tmp):
    r = client.post("/api/galeria/editar", data={"idea": "x"},
                    files={"imagen": ("a.png", _png("RGBA"), "image/png")})
    with Image.open(imagen_libre.ruta_fuente(r.json()["id"])) as im:
        assert im.mode == "RGB"


def test_crear_editar_con_archivo_que_no_es_imagen_400(client, dirs_tmp):
    r = client.post("/api/galeria/editar", data={"idea": "x"},
                    files={"imagen": ("a.png", b"no soy una imagen", "image/png")})
    assert r.status_code == 400 and "No se pudo leer" in r.json()["detail"]


def test_crear_editar_con_idea_vacia_400_y_sin_imagen_422(client, dirs_tmp):
    r = client.post("/api/galeria/editar", data={"idea": " "},
                    files={"imagen": ("a.png", _png(), "image/png")})
    assert r.status_code == 400
    assert client.post("/api/galeria/editar", data={"idea": "x"}).status_code == 422


def test_crear_editar_con_motor_que_solo_genera_400(client, dirs_tmp):
    r = client.post("/api/galeria/editar", data={"idea": "x", "motor": "zimage"},
                    files={"imagen": ("a.png", _png(), "image/png")})
    assert r.status_code == 400


def test_quitar_fondo_encola_y_guarda_la_fuente(client, dirs_tmp, jobs_encolados):
    r = client.post("/api/galeria/quitarfondo", files={"imagen": ("foto.png", _png(), "image/png")})
    body = r.json()
    assert r.status_code == 200 and jobs_encolados == [("quitar_fondo", body["id"])]
    assert imagen_libre.ruta_fuente(body["id"]).exists()
    assert client.get(f"/api/galeria/{body['id']}").json()["idea"] == "foto.png"


def test_quitar_fondo_con_archivo_invalido_400(client, dirs_tmp, jobs_encolados):
    r = client.post("/api/galeria/quitarfondo", files={"imagen": ("a.png", b"basura", "image/png")})
    assert r.status_code == 400 and jobs_encolados == []


# --- listar / detalle / editar prompt --------------------------------------

def test_listar(client, img):
    assert [(x["id"], x["tipo"], x["idea"]) for x in client.get("/api/galeria").json()] == [
        (img, "generar", "un gato")]


def test_detalle_inexistente_404(client):
    assert client.get("/api/galeria/99").status_code == 404


def test_editar_prompt(client, img):
    assert client.put(f"/api/galeria/{img}/prompt", json={"prompt": "a cat"}).json() == {"ok": True}
    assert client.get(f"/api/galeria/{img}").json()["prompt"] == "a cat"
    assert client.put("/api/galeria/99/prompt", json={"prompt": "x"}).status_code == 404


def test_detalle_marca_ocupado_con_job_activo(client, session, img):
    session.add(Job(tipo="generar_previews_imagen", ref_id=img, estado="corriendo"))
    session.commit()
    assert client.get(f"/api/galeria/{img}").json()["ocupado"] is True


# --- lanzar etapas ----------------------------------------------------------

def test_mejorar_previews_y_final_encolan(client, img, jobs_encolados):
    client.post(f"/api/galeria/{img}/mejorar")
    client.post(f"/api/galeria/{img}/previews", json={"width": 500, "height": 700})
    client.post(f"/api/galeria/{img}/final", json={"indice": 2})
    assert jobs_encolados == [("mejorar_prompt_imagen", img), ("generar_previews_imagen", img),
                              ("generar_final_imagen", img)]
    assert jobs_encolados.params[2] == {"indice": 2}
    d = client.get(f"/api/galeria/{img}").json()
    assert (d["width"], d["height"]) == (512, 704)  # el tamaño de las previews se guarda


def test_previews_sin_cuerpo_conserva_el_tamano(client, img, jobs_encolados):
    assert client.post(f"/api/galeria/{img}/previews").status_code == 200
    assert client.get(f"/api/galeria/{img}").json()["width"] == 768


def test_previews_con_solo_un_lado_no_cambia_nada(client, img):
    client.post(f"/api/galeria/{img}/previews", json={"width": 300})
    assert client.get(f"/api/galeria/{img}").json()["width"] == 768


@pytest.mark.parametrize("ruta,cuerpo", [
    ("mejorar", None), ("previews", {}), ("final", {"indice": 0})])
def test_etapas_de_imagen_inexistente_404(client, jobs_encolados, ruta, cuerpo):
    assert client.post(f"/api/galeria/99/{ruta}", json=cuerpo).status_code == 404
    assert jobs_encolados == []


def test_final_sin_indice_422(client, img):
    assert client.post(f"/api/galeria/{img}/final", json={}).status_code == 422


# --- borrar y archivos ------------------------------------------------------

def test_borrar_quita_fila_y_carpeta(client, session, img, dirs_tmp):
    carpeta = imagen_libre.carpeta(img)
    carpeta.mkdir(parents=True)
    (carpeta / "preview_0.png").write_bytes(b"x")
    assert client.delete(f"/api/galeria/{img}").json() == {"borrada": img, "archivos": 1}
    assert not carpeta.exists()
    assert galeria_repo.obtener(session, img) is None
    assert client.delete(f"/api/galeria/{img}").status_code == 404


@pytest.mark.parametrize("ruta", ["fuente", "preview/0", "final"])
def test_archivos_404_hasta_que_existen(client, img, dirs_tmp, ruta):
    assert client.get(f"/api/galeria/{img}/{ruta}").status_code == 404
    carpeta = imagen_libre.carpeta(img)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = {"fuente": "fuente.png", "preview/0": "preview_0.png", "final": "final.png"}[ruta]
    (carpeta / nombre).write_bytes(b"png")
    r = client.get(f"/api/galeria/{img}/{ruta}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
