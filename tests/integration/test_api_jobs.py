import pytest

from backend.models import Job
from backend.services import cancelacion

pytestmark = pytest.mark.integration


@pytest.fixture
def sin_comfy(monkeypatch):
    """La parada no habla con ComfyUI ni mata procesos; registra que lo pidió."""
    pedidos = []
    monkeypatch.setattr(cancelacion.comfy, "interrumpir", lambda: pedidos.append("comfy"))
    monkeypatch.setattr(cancelacion.procesos, "terminar_actual",
                        lambda: pedidos.append("procesos") or 0)
    yield pedidos
    cancelacion.limpiar()


def _job(session, tipo="generar_imagenes", estado="pendiente", **kw):
    j = Job(tipo=tipo, ref_id=1, estado=estado, **kw)
    session.add(j)
    session.commit()
    return j


def test_job_inexistente_404(client):
    assert client.get("/api/jobs/123").status_code == 404
    assert client.post("/api/jobs/123/cancelar").status_code == 404


def test_ver_job_y_listado_de_activos(client, session):
    j = _job(session, tipo="generar_ideas")

    r = client.get(f"/api/jobs/{j.id}")
    assert r.status_code == 200
    assert r.json()["estado"] == "pendiente"
    assert r.json()["progreso"] is None
    assert r.json()["intentos"] == 0

    assert [x["id"] for x in client.get("/api/jobs").json()] == [j.id]


def test_cancelar_un_pendiente_lo_deja_fuera_de_la_cola(client, session, sin_comfy):
    j = _job(session)

    r = client.post(f"/api/jobs/{j.id}/cancelar")

    assert r.json() == {"id": j.id, "estado": "cancelado", "cortado": False}
    # Nada que cortar en caliente: no estaba corriendo.
    assert sin_comfy == []
    assert client.get("/api/jobs").json() == []
    assert client.get(f"/api/jobs/{j.id}").json()["estado"] == "cancelado"


def test_cancelar_el_que_corre_lo_corta_en_caliente(client, session, sin_comfy):
    j = _job(session, estado="corriendo")
    cancelacion.iniciar(j.id)

    r = client.post(f"/api/jobs/{j.id}/cancelar")

    assert r.json()["cortado"] is True
    assert sin_comfy == ["comfy", "procesos"]
    assert cancelacion.pedida() is True


def test_cancelar_un_job_terminado_no_reescribe_su_resultado(client, session, sin_comfy):
    j = _job(session, estado="error")

    r = client.post(f"/api/jobs/{j.id}/cancelar")

    assert r.json() == {"id": j.id, "estado": "error", "cortado": False}


def test_parar_corta_el_que_corre_y_vacia_la_cola(client, session, sin_comfy):
    corriendo = _job(session, estado="corriendo")
    cancelacion.iniciar(corriendo.id)
    _job(session)
    _job(session, tipo="generar_clips")

    r = client.post("/api/jobs/parar")

    assert r.json() == {"corriendo": 1, "pendientes": 2, "cortado": True}
    assert client.get("/api/jobs").json() == []


def test_parar_solo_la_cola_deja_acabar_la_etapa_en_curso(client, session, sin_comfy):
    """Para no tirar los minutos de GPU que la etapa ya lleva invertidos."""
    corriendo = _job(session, estado="corriendo")
    cancelacion.iniciar(corriendo.id)
    _job(session)

    r = client.post("/api/jobs/parar", json={"corriendo": False, "pendientes": True})

    assert r.json() == {"corriendo": 0, "pendientes": 1, "cortado": False}
    assert sin_comfy == []
    assert [x["id"] for x in client.get("/api/jobs").json()] == [corriendo.id]


def test_el_historial_distingue_cancelado_de_error_y_cuenta_los_intentos(client, session):
    _job(session, estado="ok", intentos=1)
    _job(session, tipo="generar_clips", estado="error", intentos=3,
         log="Falló 3 veces; el último error:\nComfyError")
    _job(session, tipo="generar_i2v", estado="cancelado", intentos=1,
         log="Parado desde la interfaz")
    _job(session, tipo="generar_voz")        # pendiente: aún no es historia

    historial = client.get("/api/jobs/historial").json()

    # Del más reciente al más viejo.
    assert [(h["tipo"], h["estado"], h["intentos"]) for h in historial] == [
        ("generar_i2v", "cancelado", 1),
        ("generar_clips", "error", 3),
        ("generar_imagenes", "ok", 1),
    ]
    assert "Falló 3 veces" in historial[1]["log"]


def test_el_historial_se_puede_acotar(client, session):
    for _ in range(4):
        _job(session, estado="ok")

    assert len(client.get("/api/jobs/historial?limite=2").json()) == 2
