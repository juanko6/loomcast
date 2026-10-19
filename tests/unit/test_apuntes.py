import pytest

from backend.services import apuntes


@pytest.fixture(autouse=True)
def limpio():
    apuntes.limpiar()
    yield
    apuntes.limpiar()


def test_fuera_de_un_job_los_apuntes_se_descartan():
    """Quien anota no sabe si hay un job abierto: si le llaman desde un hilo
    HTTP, la línea se tira en vez de acabar pegada al log del siguiente job."""
    apuntes.anotar("algo")
    assert apuntes.recoger() == []


def test_se_recogen_en_orden():
    apuntes.iniciar()
    apuntes.anotar("primero")
    apuntes.anotar("segundo")
    assert apuntes.recoger() == ["primero", "segundo"]


def test_iniciar_tira_lo_del_job_anterior():
    apuntes.iniciar()
    apuntes.anotar("del job viejo")
    apuntes.iniciar()
    assert apuntes.recoger() == []


def test_recoger_no_vacia():
    """La cola recoge dentro del try y limpia en el finally: dos lecturas
    seguidas tienen que dar lo mismo."""
    apuntes.iniciar()
    apuntes.anotar("x")
    assert apuntes.recoger() == apuntes.recoger() == ["x"]
