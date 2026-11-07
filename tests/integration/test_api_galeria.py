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


# --- animada -----------------------------------------------------------------

def _animada(client, dirs_tmp, estado="final"):
    """Una animada con la preview 1 ya aprobada (o en el estado pedido)."""
    from backend.db import get_session

    iid = client.post("/api/galeria/animada", json={"idea": "un gato groovy"}).json()["id"]
    carpeta = imagen_libre.carpeta(iid)
    carpeta.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        Image.new("RGB", (8, 8), (i * 40, 0, 0)).save(imagen_libre.ruta_preview(iid, i))
    with get_session() as s:
        img = galeria_repo.obtener(s, iid)
        img.estado, img.seeds = "previews", "[1, 2, 3, 4]"
        s.commit()
    if estado != "previews":
        assert client.post(f"/api/galeria/{iid}/final", json={"indice": 1}).json() == {"job_id": None}
        with get_session() as s:
            galeria_repo.obtener(s, iid).estado = estado
            s.commit()
    return iid


def test_crear_animada_usa_el_motor_de_generar(client, dirs_tmp, jobs_encolados):
    r = client.post("/api/galeria/animada", json={"idea": "  un faro  ", "width": 700, "height": 1300})
    d = client.get(f"/api/galeria/{r.json()['id']}").json()
    assert (d["tipo"], d["idea"], d["motor"], d["estado"]) == ("animada", "un faro", "zimage", "nueva")
    assert (d["width"], d["height"]) == (704, 1280)
    assert (d["prompt_movimiento"], d["duracion_s"], d["videos"]) == ("", 12, [])
    assert jobs_encolados == []


def test_crear_animada_sin_idea_400(client):
    assert client.post("/api/galeria/animada", json={"idea": " "}).status_code == 400


def test_aprobar_preview_de_animada_no_encola_esrgan(client, dirs_tmp, jobs_encolados):
    iid = _animada(client, dirs_tmp)
    assert jobs_encolados == []
    d = client.get(f"/api/galeria/{iid}").json()
    assert (d["estado"], d["seed_elegido"]) == ("final", 1)
    assert imagen_libre.ruta_final(iid).read_bytes() == imagen_libre.ruta_preview(iid, 1).read_bytes()


def test_aprobar_preview_inexistente_de_animada_400(client, dirs_tmp):
    iid = _animada(client, dirs_tmp, estado="previews")
    assert client.post(f"/api/galeria/{iid}/final", json={"indice": 7}).status_code == 400


def test_movimiento_se_guarda_acotado_y_encola_mejorar_animar_y_escalar(client, dirs_tmp, jobs_encolados):
    iid = _animada(client, dirs_tmp)
    r = client.put(f"/api/galeria/{iid}/movimiento", json={"prompt": " se balancea ", "duracion_s": 14})
    assert r.status_code == 200
    d = client.get(f"/api/galeria/{iid}").json()
    assert (d["prompt_movimiento"], d["duracion_s"], d["estado"]) == ("se balancea", 14, "movimiento")

    assert client.post(f"/api/galeria/{iid}/movimiento/mejorar").status_code == 200
    assert client.post(f"/api/galeria/{iid}/animar").status_code == 200
    # Sin vídeo no hay nada que escalar.
    assert client.post(f"/api/galeria/{iid}/escalar", json={"escala": "4k"}).status_code == 409
    from backend.services.pipeline import imagen_animada

    imagen_animada.ruta_video(iid).write_bytes(b"mp4")
    assert client.post(f"/api/galeria/{iid}/escalar", json={"escala": "4k"}).status_code == 200
    assert jobs_encolados == [("mejorar_movimiento_animada", iid), ("animar_imagen", iid),
                              ("escalar_animada", iid)]
    assert jobs_encolados.params[2] == {"escala": "4k"}


@pytest.mark.parametrize("dur", [9, 16])
def test_movimiento_con_duracion_fuera_de_rango_422(client, dirs_tmp, dur):
    iid = _animada(client, dirs_tmp)
    r = client.put(f"/api/galeria/{iid}/movimiento", json={"prompt": "x", "duracion_s": dur})
    assert r.status_code == 422


def test_cambiar_el_movimiento_no_esconde_el_video_que_ya_hay(client, dirs_tmp):
    iid = _animada(client, dirs_tmp, estado="escalada")
    client.put(f"/api/galeria/{iid}/movimiento", json={"prompt": "otro", "duracion_s": 10})
    assert client.get(f"/api/galeria/{iid}").json()["estado"] == "escalada"


def test_pasos_de_animada_antes_de_aprobar_o_en_otro_tipo_409(client, dirs_tmp, img, jobs_encolados):
    sin_aprobar = _animada(client, dirs_tmp, estado="previews")
    for iid in (sin_aprobar, img):
        assert client.put(f"/api/galeria/{iid}/movimiento",
                          json={"prompt": "x", "duracion_s": 12}).status_code == 409
        assert client.post(f"/api/galeria/{iid}/animar").status_code == 409
    assert jobs_encolados == []


def test_mejorar_o_animar_sin_movimiento_409(client, dirs_tmp, jobs_encolados):
    iid = _animada(client, dirs_tmp)
    assert client.post(f"/api/galeria/{iid}/movimiento/mejorar").status_code == 409
    assert client.post(f"/api/galeria/{iid}/animar").status_code == 409
    assert jobs_encolados == []


def test_movimiento_vacio_400_y_escala_rara_422(client, dirs_tmp):
    iid = _animada(client, dirs_tmp)
    assert client.put(f"/api/galeria/{iid}/movimiento", json={"prompt": "  "}).status_code == 400
    assert client.post(f"/api/galeria/{iid}/escalar", json={"escala": "8k"}).status_code == 422


@pytest.mark.parametrize("ruta,metodo,cuerpo", [
    ("movimiento", "put", {"prompt": "x"}), ("movimiento/mejorar", "post", None),
    ("animar", "post", None), ("escalar", "post", {"escala": "2k"})])
def test_pasos_de_animada_inexistente_404(client, ruta, metodo, cuerpo):
    assert getattr(client, metodo)(f"/api/galeria/99/{ruta}", json=cuerpo).status_code == 404


def test_video_y_versiones_escaladas(client, dirs_tmp):
    from backend.services.pipeline import imagen_animada

    iid = _animada(client, dirs_tmp, estado="escalada")
    assert client.get(f"/api/galeria/{iid}/video").status_code == 404
    imagen_animada.ruta_video(iid).write_bytes(b"base")
    imagen_animada.ruta_video(iid, "4k").write_bytes(b"cuatro")
    imagen_animada.ruta_video(iid, "1080p").write_bytes(b"fullhd")
    r = client.get(f"/api/galeria/{iid}/video")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and r.content == b"base"
    assert client.get(f"/api/galeria/{iid}/video?escala=4k").content == b"cuatro"
    assert client.get(f"/api/galeria/{iid}/video?escala=2k").status_code == 404
    assert client.get(f"/api/galeria/{iid}/video?escala=8k").status_code == 400
    assert client.get(f"/api/galeria/{iid}/video?escala=1080p").content == b"fullhd"
    assert client.get(f"/api/galeria/{iid}").json()["videos"] == ["base", "1080p", "4k"]


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
