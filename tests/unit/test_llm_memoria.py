"""El guardia de memoria de `llm_runtime`: no lanzar un modelo si no cabe.

Es lo que faltaba el 2026-10-19, cuando ComfyUI retenía 11,7 GiB de Z-Image y
encima se lanzó un MLX de ~20 GiB: el kernel mató al backend con `Killed: 9`.
"""
import pytest

from backend.clients import comfy
from backend.services import apuntes, llm_runtime


@pytest.fixture
def modelo():
    return llm_runtime.modelos()[0]


@pytest.fixture(autouse=True)
def apuntes_de_un_job():
    apuntes.iniciar()
    yield
    apuntes.limpiar()


def _liberacion(logrado, antes=16.4, despues=27.0):
    def liberar(hasta_gb=None):
        liberar.hasta_gb = hasta_gb
        return comfy.Liberacion(antes, despues, 1.7, 1, logrado)

    liberar.hasta_gb = None
    return liberar


def test_pide_la_memoria_que_declara_el_modelo(monkeypatch, modelo):
    liberar = _liberacion(True)
    monkeypatch.setattr(llm_runtime.comfy, "liberar_memoria", liberar)
    llm_runtime._hacer_sitio(modelo)
    assert liberar.hasta_gb == modelo.memoria_gb


def test_el_antes_y_despues_queda_en_el_job(monkeypatch, modelo):
    monkeypatch.setattr(llm_runtime.comfy, "liberar_memoria", _liberacion(True))
    llm_runtime._hacer_sitio(modelo)
    assert apuntes.recoger() == [
        f"Memoria para «{modelo.nombre}» ({modelo.memoria_gb:.0f} GiB): "
        "16.4 → 27.0 GiB libres (+10.6 en 1.7 s, 1 petición a /free)"
    ]


def test_el_antes_y_despues_tambien_sale_por_el_log_del_backend(
    monkeypatch, modelo, capsys
):
    monkeypatch.setattr(llm_runtime.comfy, "liberar_memoria", _liberacion(True))
    llm_runtime._hacer_sitio(modelo)
    assert "[llm] Memoria para" in capsys.readouterr().out


def test_si_la_memoria_no_baja_no_se_lanza(monkeypatch, modelo):
    monkeypatch.setattr(
        llm_runtime.comfy, "liberar_memoria", _liberacion(False, 16.4, 16.4)
    )
    with pytest.raises(llm_runtime.LLMProcesoError) as e:
        llm_runtime._hacer_sitio(modelo)
    # El mensaje tiene que llevar la medición: es lo que se lee en el historial.
    assert "16.4" in str(e.value) and "Killed: 9" in str(e.value)


def test_asegurar_no_arranca_el_proceso_si_no_hay_memoria(monkeypatch, modelo):
    """El cierre del agujero: antes de esto `asegurar()` llamaba al /free y
    lanzaba acto seguido, con los modelos de ComfyUI todavía dentro."""
    lanzados = []
    monkeypatch.setattr(
        llm_runtime.comfy, "liberar_memoria", _liberacion(False, 16.4, 16.4)
    )
    monkeypatch.setattr(llm_runtime.llm, "ping", lambda url: False)
    monkeypatch.setattr(llm_runtime, "_lanzar", lambda m: lanzados.append(m))
    monkeypatch.setattr(llm_runtime, "activo", lambda: modelo)
    monkeypatch.setattr(type(modelo), "gestionado", property(lambda self: True))
    with pytest.raises(llm_runtime.LLMProcesoError):
        llm_runtime.asegurar()
    assert lanzados == []


def test_si_comfy_no_responde_se_lanza_igual(monkeypatch, modelo):
    """Un ComfyUI caído no retiene nada, y Loomcast se usa también sin él
    (`run-loomcast.sh --sin-comfy`): sin medición no se bloquea el modelo."""
    def liberar(hasta_gb=None):
        return comfy.Liberacion(None, None, 0.0, 0, True)

    monkeypatch.setattr(llm_runtime.comfy, "liberar_memoria", liberar)
    llm_runtime._hacer_sitio(modelo)  # no lanza
    assert apuntes.recoger() == [
        f"Memoria para «{modelo.nombre}» ({modelo.memoria_gb:.0f} GiB): "
        "ComfyUI no responde, no se pudo medir la memoria"
    ]
