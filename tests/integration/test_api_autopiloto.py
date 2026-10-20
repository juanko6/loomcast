"""La cara HTTP del autopiloto y de los lotes.

Aquí la cola está sustituida (fixture `client`): lo que se comprueba es lo que
contesta la API y el estado que deja escrito, no que las etapas corran. De eso
se encarga `test_autopiloto.py` con la cola de verdad.
"""
import pytest

from backend.repositories import autopilotos as autopilotos_repo
from backend.repositories import voces as voces_repo
from tests import factories as f

pytestmark = pytest.mark.integration


@pytest.fixture
def proy(session, dirs_tmp):
    """Un proyecto con su voz elegida: es lo que el autopiloto exige."""
    p = f.proyecto(session)
    voces_repo.crear(session, "narrador", "Narrador", "instruct")
    session.commit()
    p.voz = "narrador"
    session.commit()
    return p


# --- lanzar un proyecto -----------------------------------------------------

def test_lanzar_devuelve_el_estado_y_las_paradas_por_defecto(client, proy):
    r = client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})

    assert r.status_code == 200
    d = r.json()
    assert d["estado"] == "corriendo"
    assert d["modo_video"] == "estatico"
    assert d["paradas"] == ["idea", "guion", "escenas"]


def test_lanzar_sin_paradas_es_produccion_sin_manos(client, proy):
    d = client.post(
        f"/api/proyectos/{proy.id}/autopiloto",
        json={"modo": "estatico", "paradas": []},
    ).json()

    assert d["paradas"] == []


def test_lanzar_elige_la_voz_de_paso(client, session, dirs_tmp):
    p = f.proyecto(session)
    voces_repo.crear(session, "otra", "Otra", "instruct")
    session.commit()

    r = client.post(
        f"/api/proyectos/{p.id}/autopiloto",
        json={"modo": "estatico", "voz": "otra"},
    )

    assert r.status_code == 200
    session.expire_all()
    assert session.get(type(p), p.id).voz == "otra"


def test_lanzar_sin_voz_ni_elegida_ni_puesta_es_400(client, session, dirs_tmp):
    p = f.proyecto(session)

    r = client.post(f"/api/proyectos/{p.id}/autopiloto", json={"modo": "estatico"})

    assert r.status_code == 400 and "voz" in r.text


def test_lanzar_con_una_voz_que_no_existe_es_400(client, proy):
    r = client.post(
        f"/api/proyectos/{proy.id}/autopiloto",
        json={"modo": "estatico", "voz": "fantasma"},
    )

    assert r.status_code == 400


def test_lanzar_dos_veces_es_409(client, proy):
    client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})

    r = client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})

    assert r.status_code == 409


def test_lanzar_con_un_modo_o_una_parada_inventados_es_400(client, proy):
    assert client.post(
        f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "holograma"}
    ).status_code == 400
    assert client.post(
        f"/api/proyectos/{proy.id}/autopiloto",
        json={"modo": "estatico", "paradas": ["musica"]},
    ).status_code == 400


def test_lanzar_sobre_un_proyecto_que_no_existe_es_404(client):
    assert client.post("/api/proyectos/999/autopiloto", json={}).status_code == 404


# --- continuar y detener ----------------------------------------------------

def test_continuar_sin_revision_pendiente_es_409(client, proy):
    client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})

    r = client.post(f"/api/proyectos/{proy.id}/autopiloto/continuar")

    assert r.status_code == 409


def test_continuar_lo_pone_a_producir_otra_vez(client, session, proy):
    client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})
    auto = autopilotos_repo.vivo_de_proyecto(session, proy.id)
    autopilotos_repo.marcar(session, auto, "esperando", "Esperando que revises el guion",
                            etapa="generar_guion")
    session.commit()

    d = client.post(f"/api/proyectos/{proy.id}/autopiloto/continuar").json()

    assert d["estado"] == "corriendo"


def test_detener_lo_apaga(client, proy):
    client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})

    d = client.delete(f"/api/proyectos/{proy.id}/autopiloto").json()

    assert d["parado"] is True
    assert client.get(f"/api/proyectos/{proy.id}").json()["autopiloto"]["estado"] == "parado"


def test_detener_sin_autopiloto_no_es_un_error(client, proy):
    assert client.delete(f"/api/proyectos/{proy.id}/autopiloto").json() == {
        "parado": False
    }


# --- el detalle y el listado del proyecto -----------------------------------

def test_el_detalle_lleva_el_autopiloto_y_la_parada_en_la_que_espera(client, session,
                                                                     proy):
    client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})
    auto = autopilotos_repo.vivo_de_proyecto(session, proy.id)
    autopilotos_repo.marcar(session, auto, "esperando", "Esperando que revises el guion",
                            etapa="generar_guion")
    session.commit()

    d = client.get(f"/api/proyectos/{proy.id}").json()["autopiloto"]

    assert d["estado"] == "esperando" and d["parada"] == "guion"
    assert d["motivo"] == "Esperando que revises el guion"


def test_el_listado_marca_los_proyectos_en_automatico(client, proy):
    client.post(f"/api/proyectos/{proy.id}/autopiloto", json={"modo": "estatico"})

    fila = client.get("/api/proyectos").json()[0]

    assert fila["autopiloto"] == "corriendo"


# --- lotes ------------------------------------------------------------------

@pytest.fixture
def tema_con_aprobadas(session, dirs_tmp):
    t = f.tema(session)
    for k in range(3):
        idea = f.idea(session, t.id, titulo=f"Idea {k}")
        idea.estado = "aprobada" if k < 2 else "propuesta"
    voces_repo.crear(session, "narrador", "Narrador", "instruct")
    session.commit()
    return t


def test_lanzar_un_lote_crea_un_proyecto_por_idea_aprobada(client, tema_con_aprobadas):
    r = client.post("/api/lotes", json={
        "tema_id": tema_con_aprobadas.id, "modo": "estatico", "voz": "narrador",
    })

    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 2                      # la propuesta no entra
    assert d["pendientes"] == 1                 # uno produce, el otro espera
    assert d["actual"]["posicion"] == 1
    assert len(client.get("/api/proyectos").json()) == 2


def test_sin_la_parada_de_ideas_el_lote_coge_tambien_las_propuestas(
    client, tema_con_aprobadas
):
    d = client.post("/api/lotes", json={
        "tema_id": tema_con_aprobadas.id, "modo": "estatico",
        "voz": "narrador", "paradas": [],
    }).json()

    assert d["total"] == 3


def test_un_tema_sin_ideas_aprobadas_explica_que_hacer(client, session, dirs_tmp):
    t = f.tema(session)
    f.idea(session, t.id)
    voces_repo.crear(session, "narrador", "Narrador", "instruct")
    session.commit()

    r = client.post("/api/lotes", json={"tema_id": t.id, "voz": "narrador"})

    assert r.status_code == 400
    assert "Aprueba" in r.text


def test_lote_de_un_tema_que_no_existe_es_404(client):
    assert client.post("/api/lotes", json={"tema_id": 999}).status_code == 404


def test_listar_y_ver_un_lote(client, tema_con_aprobadas):
    creado = client.post("/api/lotes", json={
        "tema_id": tema_con_aprobadas.id, "modo": "estatico", "voz": "narrador",
    }).json()

    assert client.get("/api/lotes").json()[0]["id"] == creado["id"]
    visto = client.get(f"/api/lotes/{creado['id']}").json()
    assert visto["tema"] == "el espacio"
    assert [x["estado"] for x in visto["proyectos"]] == ["corriendo", "pendiente"]
    assert client.get("/api/lotes/999").status_code == 404


def test_parar_desde_la_interfaz_cuenta_los_autopilotos_que_apaga(client,
                                                                 tema_con_aprobadas):
    client.post("/api/lotes", json={
        "tema_id": tema_con_aprobadas.id, "modo": "estatico", "voz": "narrador",
    })

    r = client.post("/api/jobs/parar").json()

    assert r["autopilotos"] == 2
    assert [x["estado"] for x in client.get("/api/lotes").json()[0]["proyectos"]] == [
        "parado", "parado",
    ]


def test_detener_lo_actual_no_apaga_la_linea(client, tema_con_aprobadas):
    """"Detener lo actual" corta una etapa, no el lote: lo que espera sigue
    esperando, y eso incluye los proyectos que aún no han empezado."""
    client.post("/api/lotes", json={
        "tema_id": tema_con_aprobadas.id, "modo": "estatico", "voz": "narrador",
    })

    r = client.post("/api/jobs/parar", json={"corriendo": True, "pendientes": False})

    assert r.json()["autopilotos"] == 0
    assert [x["estado"] for x in client.get("/api/lotes").json()[0]["proyectos"]] == [
        "corriendo", "pendiente",
    ]
