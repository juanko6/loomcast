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
    # True = el puerto quedó libre. Devolver None aquí haría que el código
    # entrara a rematar el puerto y `lsof` mataría de verdad a quien estuviera
    # escuchando en el 9876 de esta máquina.
    monkeypatch.setattr(llm_runtime, "_esperar_puerto_libre", lambda url: True)
    monkeypatch.setattr(
        llm_runtime, "_rematar_el_puerto", lambda url: pytest.fail("no tocaba rematar")
    )
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


# --- hacerse cargo del llama-server que ya estaba puesto --------------------
# El agujero del 2026-10-23: `asegurar()` usaba para las etapas de texto un
# servidor que no había arrancado («se adopta y no se toca»), pero `liberar()`
# solo miraba `_proc`, así que no lo paraba nunca. Con un 27B de 16,7 GiB a mano
# en el 9876, generar la voz de un episodio se fue 18,4 GiB al swap: el kernel
# sacó ese modelo a trocitos para hacerle sitio al TTS, y narrar 77 s de audio
# costó 4 min 39 s.

@pytest.fixture
def puesto(monkeypatch):
    """Ya hay un llama-server escuchando que no arrancó Loomcast."""
    monkeypatch.setattr(llm_runtime.llm, "ping", lambda url=None: True)
    monkeypatch.setattr(
        llm_runtime.llm, "que_hay", lambda url=None: ("Qwen3.6-27B", 16.7)
    )
    monkeypatch.setattr(llm_runtime, "_pids_en_puerto", lambda url: [4242])
    monkeypatch.setattr(llm_runtime.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(llm_runtime, "_vive", lambda pgid: True)


@pytest.fixture
def activo(monkeypatch, modelo):
    monkeypatch.setattr(llm_runtime, "activo", lambda: modelo)
    monkeypatch.setattr(
        llm_runtime, "_lanzar", lambda m: pytest.fail("no tocaba lanzar nada")
    )
    return modelo


def test_asegurar_se_hace_cargo_del_que_ya_estaba(puesto, activo):
    llm_runtime.asegurar()
    assert llm_runtime._tomado == 4242
    assert llm_runtime._proc_modelo == activo.id


def test_lo_que_encontro_puesto_se_para_antes_de_la_voz(monkeypatch, puesto, activo):
    """El arreglo: antes de esto `liberar()` no lo tocaba y sus GiB seguían
    dentro mientras el TTS cargaba encima."""
    muertos, esperas = [], []
    monkeypatch.setattr(llm_runtime, "_matar_pgid", muertos.append)
    monkeypatch.setattr(llm_runtime, "_esperar_puerto_libre", lambda url: True)
    monkeypatch.setattr(llm_runtime.memoria, "disponible_gb", lambda: 9.0)
    monkeypatch.setattr(
        llm_runtime, "_esperar_devolucion", lambda gb, antes: esperas.append((gb, antes))
    )

    llm_runtime.asegurar()
    llm_runtime.liberar("empieza generar_voz")

    assert muertos == [4242]
    # Y se espera a *sus* GiB, los que dijo tener dentro, no los que declare
    # config.toml de otro modelo: comparten puerto, pueden no ser el mismo.
    assert esperas == [(16.7, 9.0)]
    assert llm_runtime._tomado is None


def test_se_anota_que_hay_en_el_puerto_aunque_no_sea_el_elegido(puesto, activo):
    """Todos tus scripts comparten el 9876, así que lo que responde ahí puede
    no ser el modelo que marca la UI. Es lo que explica un guion escrito por un
    modelo que no habías elegido, y por eso va al historial del job."""
    llm_runtime.asegurar()
    anotado = apuntes.recoger()[0]
    assert "Qwen3.6-27B" in anotado and "16.7 GiB" in anotado


def test_solo_se_toma_el_mando_una_vez(puesto, activo):
    for _ in range(3):
        llm_runtime.asegurar()
    assert len(apuntes.recoger()) == 1


def test_si_no_se_encuentra_su_proceso_se_avisa_de_que_no_se_podra_parar(
    monkeypatch, puesto, activo
):
    """Sin pid no hay nada que matar, y callarlo es dejar al usuario buscando
    por qué el TTS se va al swap."""
    monkeypatch.setattr(llm_runtime, "_pids_en_puerto", lambda url: [])
    llm_runtime.asegurar()
    assert llm_runtime._tomado is None
    assert "no se podrá parar" in apuntes.recoger()[0]


def test_un_modelo_externo_no_se_toca(monkeypatch, modelo, puesto):
    """Sin `comando` en config.toml el servidor es tuyo: ni se arranca ni se
    para. Es el único caso en que la memoria de otro sigue dentro, y ahí lo
    correcto es no tocarla."""
    import dataclasses

    externo = dataclasses.replace(modelo, comando=None)
    monkeypatch.setattr(llm_runtime, "activo", lambda: externo)
    monkeypatch.setattr(
        llm_runtime, "_lanzar", lambda m: pytest.fail("no tocaba lanzar nada")
    )
    llm_runtime.asegurar()
    assert llm_runtime._tomado is None and apuntes.recoger() == []


def test_al_apagar_no_se_para_lo_que_no_arrancamos(monkeypatch, puesto, activo):
    """Antes de la voz sí, porque ahí su memoria es el problema; al salir no,
    porque era tuyo antes de que abriéramos."""
    monkeypatch.setattr(
        llm_runtime, "_matar_pgid", lambda pgid: pytest.fail("era tuyo")
    )
    llm_runtime.asegurar()
    llm_runtime.apagar()
    assert llm_runtime._tomado == 4242


def test_se_para_lo_puesto_aunque_ninguna_etapa_de_texto_lo_haya_usado(
    monkeypatch, puesto, modelo
):
    """El caso de verdad: arrancas Loomcast, abres un proyecto que ya tiene
    guion y pides la voz. Ninguna etapa de texto pasó por `asegurar()`, así que
    no hay nada apuntado que parar — y los 16,7 GiB del puerto estorban igual.
    """
    muertos, esperas = [], []
    monkeypatch.setattr(llm_runtime.llm, "activo", lambda: modelo)
    monkeypatch.setattr(llm_runtime, "_matar_pgid", muertos.append)
    monkeypatch.setattr(llm_runtime, "_esperar_puerto_libre", lambda url: True)
    monkeypatch.setattr(llm_runtime.memoria, "disponible_gb", lambda: 9.0)
    monkeypatch.setattr(
        llm_runtime, "_esperar_devolucion", lambda gb, antes: esperas.append(gb)
    )

    llm_runtime.liberar("empieza generar_voz")

    assert muertos == [4242] and esperas == [16.7]


def test_un_externo_puesto_no_se_para_antes_de_la_voz(monkeypatch, puesto, modelo):
    """Sin `comando` es tuyo: su memoria se queda dentro y es lo correcto."""
    import dataclasses

    monkeypatch.setattr(
        llm_runtime.llm, "activo", lambda: dataclasses.replace(modelo, comando=None)
    )
    monkeypatch.setattr(
        llm_runtime, "_matar_pgid", lambda pgid: pytest.fail("era tuyo")
    )
    llm_runtime.liberar("empieza generar_voz")
    assert llm_runtime._tomado is None
