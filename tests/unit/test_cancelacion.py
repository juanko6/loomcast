"""La parada: la bandera (backend/parada.py) y el corte en caliente."""
import pytest

from backend import parada
from backend.services import cancelacion


@pytest.fixture(autouse=True)
def bandera_limpia():
    yield
    parada.limpiar()


@pytest.fixture
def cortes(monkeypatch):
    """Registra qué se corta en vez de hablar con ComfyUI o matar procesos."""
    hechos = []
    monkeypatch.setattr(cancelacion.comfy, "interrumpir", lambda: hechos.append("comfy"))
    monkeypatch.setattr(cancelacion.procesos, "terminar_actual",
                        lambda: hechos.append("procesos") or 1)
    return hechos


# --- la bandera -------------------------------------------------------------

def test_sin_job_en_curso_no_hay_nada_que_marcar():
    assert parada.marcar(7) is False
    assert parada.pedida() is False


def test_marcar_el_job_en_curso_enciende_la_bandera():
    parada.iniciar(7)

    assert parada.marcar(7) is True

    assert parada.pedida() is True
    with pytest.raises(parada.Parado, match="quedaban 3 clips"):
        parada.comprobar("quedaban 3 clips")


def test_marcar_otro_job_no_toca_al_que_corre():
    parada.iniciar(7)

    assert parada.marcar(8) is False

    assert parada.pedida() is False
    parada.comprobar()      # no levanta


def test_la_parada_no_se_hereda_al_job_siguiente():
    parada.iniciar(7)
    parada.marcar(7)

    parada.iniciar(8)

    assert parada.pedida() is False
    parada.comprobar()


def test_limpiar_deja_la_cola_sin_job_en_curso():
    parada.iniciar(7)
    parada.marcar(7)

    parada.limpiar()

    assert parada.pedida() is False
    assert parada.marcar(7) is False


# --- el corte en caliente ---------------------------------------------------

def test_pedir_corta_comfy_y_el_proceso_externo(cortes):
    parada.iniciar(7)

    assert cancelacion.pedir(7) is True

    assert cortes == ["comfy", "procesos"]
    assert parada.pedida() is True


def test_pedir_un_job_que_no_corre_no_corta_nada(cortes):
    parada.iniciar(7)

    assert cancelacion.pedir(8) is False

    assert cortes == []
    assert parada.pedida() is False


def test_las_etapas_que_no_se_cortan_a_mitad_estan_declaradas():
    """La UI y el log del job las usan para no prometer lo que no pueden."""
    assert set(cancelacion.SIN_CORTE) == {"generar_voz", "crear_voz", "clonar_voz"}
