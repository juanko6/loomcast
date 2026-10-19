import httpx
import pytest

from backend.clients import llm
from backend.services import llm_runtime

pytestmark = pytest.mark.integration


@pytest.fixture
def llm_restaurado():
    """`seleccionar` reconfigura el cliente global del LLM: se deja como estaba."""
    base = llm.activo()
    yield
    llm.configurar(base)


def test_plantillas_lista_las_del_repo(client):
    assert {"curiosidades", "drama", "historia"} <= set(
        client.get("/api/plantillas").json()
    )


def test_listar_modelos_llm(client):
    r = client.get("/api/llm/modelos").json()
    assert r["activo"] == llm_runtime.modelos()[0].id
    assert [m["id"] for m in r["modelos"]] == [m.id for m in llm_runtime.modelos()]


def test_elegir_modelo_llm_persiste_la_eleccion(client, llm_restaurado):
    otro = llm_runtime.modelos()[1]
    r = client.post("/api/llm/modelo", json={"id": otro.id})
    assert r.json() == {"id": otro.id, "nombre": otro.nombre}
    assert client.get("/api/llm/modelos").json()["activo"] == otro.id


def test_elegir_modelo_inexistente_404_y_no_cambia_el_activo(client, llm_restaurado):
    antes = client.get("/api/llm/modelos").json()["activo"]
    assert client.post("/api/llm/modelo", json={"id": "no-existe"}).status_code == 404
    assert client.get("/api/llm/modelos").json()["activo"] == antes


def test_elegir_modelo_sin_id_422(client):
    assert client.post("/api/llm/modelo", json={}).status_code == 422


def test_salud_con_comfy_arriba(client, http_mock):
    http_mock(lambda r: httpx.Response(200, json={}))
    r = client.get("/api/salud").json()
    assert r["comfy"] is True
    # Modelo gestionado y descargado: no es un fallo, el semáforo no se pone en rojo.
    assert r["llm"] is True and r["llm_estado"]["estado"] == "en_espera"


def test_salud_con_comfy_caido(client, http_mock):
    def handler(request):
        raise httpx.ConnectError("caído")

    http_mock(handler)
    assert client.get("/api/salud").json()["comfy"] is False


def test_salud_con_comfy_que_responde_error(client, http_mock):
    http_mock(lambda r: httpx.Response(500))
    assert client.get("/api/salud").json()["comfy"] is False
