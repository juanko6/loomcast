"""La parada del job en curso: las tres vías y la bandera de los bucles."""
import pytest

from backend.services import cancelacion


@pytest.fixture
def cortes(monkeypatch):
    """Registra qué se corta en vez de hablar con ComfyUI o matar procesos."""
    hechos = []
    monkeypatch.setattr(cancelacion.comfy, "interrumpir", lambda: hechos.append("comfy"))
    monkeypatch.setattr(cancelacion.procesos, "terminar_actual",
                        lambda: hechos.append("procesos") or 1)
    yield hechos
    cancelacion.limpiar()


def test_sin_job_en_curso_no_hay_nada_que_cortar(cortes):
    assert cancelacion.pedir(7) is False
    assert cortes == []
    assert cancelacion.pedida() is False


def test_pedir_el_job_en_curso_corta_comfy_y_el_proceso_externo(cortes):
    cancelacion.iniciar(7)

    assert cancelacion.pedir(7) is True

    assert cortes == ["comfy", "procesos"]
    assert cancelacion.pedida() is True
    with pytest.raises(cancelacion.Cancelado, match="quedaban 3 clips"):
        cancelacion.comprobar("quedaban 3 clips")


def test_pedir_otro_job_no_toca_al_que_corre(cortes):
    cancelacion.iniciar(7)

    assert cancelacion.pedir(8) is False

    assert cortes == []
    assert cancelacion.pedida() is False
    cancelacion.comprobar()      # no levanta


def test_la_parada_no_se_hereda_al_job_siguiente(cortes):
    cancelacion.iniciar(7)
    cancelacion.pedir(7)

    cancelacion.iniciar(8)

    assert cancelacion.pedida() is False
    cancelacion.comprobar()


def test_limpiar_deja_la_cola_sin_job_en_curso(cortes):
    cancelacion.iniciar(7)
    cancelacion.pedir(7)

    cancelacion.limpiar()

    assert cancelacion.pedida() is False
    assert cancelacion.pedir(7) is False
