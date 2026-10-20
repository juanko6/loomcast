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


def test_sin_comfy_el_error_no_le_echa_la_culpa_a_comfy(monkeypatch, modelo):
    """Con ComfyUI cerrado, la memoria la tiene otra cosa: mandar a mirar su
    workflow es mandar a buscar donde no es. El 2026-10-20 la tenía el
    compresor, con 25,5 GiB de RAM física y 48 comprimidos dentro."""
    def liberar(hasta_gb=None):
        return comfy.Liberacion(9.6, 9.6, 0.0, 0, False)

    monkeypatch.setattr(llm_runtime.comfy, "liberar_memoria", liberar)
    with pytest.raises(llm_runtime.LLMProcesoError) as e:
        llm_runtime._hacer_sitio(modelo)
    mensaje = str(e.value)
    assert "ComfyUI no está escuchando" in mensaje and "compresor" in mensaje
    assert "workflow en marcha" not in mensaje


# --- la memoria de vuelta al soltar el modelo -------------------------------
# El otro lado del mismo error: `_matar` espera a que el proceso muera y a que
# su puerto quede libre, pero eso no es tener la memoria de vuelta. El
# 2026-10-20, generando la voz de un episodio, el TTS cargó justo detrás del
# MLX recién matado y el pico se fue casi 20 GiB al swap.

def _lecturas(monkeypatch, valores):
    """La memoria disponible devuelve `valores[i]`; el último se repite."""
    estado = {"n": 0}

    def disponible():
        i = min(estado["n"], len(valores) - 1)
        estado["n"] += 1
        return valores[i]

    monkeypatch.setattr(llm_runtime.memoria, "disponible_gb", disponible)
    return estado


def test_esperar_devolucion_vuelve_cuando_la_memoria_regresa(monkeypatch, capsys):
    # 22 GiB de modelo: con tres cuartos de vuelta (16,5) ya no falta un modelo.
    _lecturas(monkeypatch, [9.0, 12.0, 26.0])
    llm_runtime._esperar_devolucion(22, 9.0)
    salida = capsys.readouterr().out
    assert "Memoria devuelta: 9.0 → 26.0 GiB" in salida and "+17.0" in salida


def test_esperar_devolucion_no_espera_mas_del_tope(monkeypatch):
    """Si la memoria no vuelve, se anota y se sigue: la etapa de después tiene
    que correr igual, y bloquearla no la haría caber."""
    _lecturas(monkeypatch, [9.0])
    monkeypatch.setattr(llm_runtime, "LLM_ESPERA_DEVOLUCION_S", 0.05)
    monkeypatch.setattr(llm_runtime.time, "sleep", lambda s: None)
    llm_runtime._esperar_devolucion(22, 9.0)
    anotado = apuntes.recoger()[0]
    assert "Memoria devuelta: 9.0 → 9.0 GiB" in anotado and "+0.0 de los 22" in anotado


def test_esperar_devolucion_sin_medicion_no_bloquea(monkeypatch):
    monkeypatch.setattr(llm_runtime.memoria, "disponible_gb", lambda: None)
    llm_runtime._esperar_devolucion(22, 9.0)
    assert apuntes.recoger() == []


@pytest.mark.parametrize("memoria_gb,antes", [(0, 9.0), (22, None)])
def test_esperar_devolucion_cuando_no_hay_nada_que_esperar(
    monkeypatch, memoria_gb, antes
):
    llamadas = _lecturas(monkeypatch, [9.0])
    llm_runtime._esperar_devolucion(memoria_gb, antes)
    assert llamadas["n"] == 0 and apuntes.recoger() == []


def test_liberar_espera_la_devolucion_antes_de_devolver_el_control(
    monkeypatch, modelo
):
    """Es lo que evita que el TTS cargue encima de un modelo recién matado."""
    esperas = []
    monkeypatch.setattr(llm_runtime, "_proc_modelo", modelo.id)
    monkeypatch.setattr(llm_runtime, "_proc", _ProcVivo())
    monkeypatch.setattr(llm_runtime, "_matar", lambda proc: None)
    monkeypatch.setattr(llm_runtime, "_esperar_puerto_libre", lambda url: None)
    monkeypatch.setattr(llm_runtime, "_olvidar_pid", lambda: None)
    monkeypatch.setattr(llm_runtime.memoria, "disponible_gb", lambda: 9.0)
    monkeypatch.setattr(
        llm_runtime, "_esperar_devolucion", lambda gb, antes: esperas.append((gb, antes))
    )

    llm_runtime.liberar("empieza generar_voz")

    assert esperas == [(modelo.memoria_gb, 9.0)]


def test_liberar_sin_nada_cargado_no_espera_nada(monkeypatch):
    esperas = []
    monkeypatch.setattr(llm_runtime, "_proc", None)
    monkeypatch.setattr(
        llm_runtime, "_esperar_devolucion", lambda gb, antes: esperas.append(gb)
    )
    llm_runtime.liberar("empieza generar_voz")
    assert esperas == []


class _ProcVivo:
    """Un proceso que está vivo, para los caminos que solo miran eso."""

    def poll(self):
        return None
