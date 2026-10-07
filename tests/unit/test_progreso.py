import pytest

from backend.services import progreso


@pytest.fixture(autouse=True)
def limpio():
    progreso.limpiar()
    yield
    progreso.limpiar()


def test_sin_job_no_hay_snapshot():
    assert progreso.snapshot() is None


def test_job_sin_lote_solo_da_tiempo_transcurrido():
    progreso.iniciar(1, "generar_voz")
    s = progreso.snapshot()
    assert s["job_id"] == 1 and s["pct"] is None and s["eta_s"] is None and s["fase"] == ""


def test_lote_sin_job_se_ignora():
    progreso.lote(1, 5)
    assert progreso.snapshot() is None


def test_primer_elemento_no_da_estimacion(monkeypatch):
    progreso.iniciar(1, "generar_imagenes")
    progreso.lote(0, 4, "imagen")
    s = progreso.snapshot()
    assert (s["fase"], s["pct"], s["eta_s"]) == ("imagen 1 de 4", 0, None)


def test_eta_se_calcula_sobre_lo_medido(monkeypatch):
    reloj = [1000.0]
    monkeypatch.setattr(progreso.time, "time", lambda: reloj[0])
    progreso.iniciar(1, "generar_imagenes")
    progreso.lote(0, 4, "imagen")
    reloj[0] += 20          # 20 s por el primer elemento
    progreso.lote(1, 4, "imagen")
    s = progreso.snapshot()
    assert s["pct"] == 25 and s["eta_s"] == 60 and s["transcurrido_s"] == 20


def test_lote_reanudado_no_cuenta_lo_ya_hecho(monkeypatch):
    reloj = [1000.0]
    monkeypatch.setattr(progreso.time, "time", lambda: reloj[0])
    progreso.iniciar(1, "x")
    progreso.lote(3, 5, "clip")     # empieza por el cuarto
    reloj[0] += 10
    progreso.lote(4, 5, "clip")
    assert progreso.snapshot()["eta_s"] == 10


def test_fase_no_pasa_del_total():
    progreso.iniciar(1, "x")
    progreso.lote(5, 5, "escena")
    assert progreso.snapshot()["fase"] == "escena 5 de 5"
