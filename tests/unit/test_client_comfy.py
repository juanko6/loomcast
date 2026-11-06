import json

import httpx
import pytest

from backend.clients import comfy
from backend.clients.comfy import ComfyError


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    monkeypatch.setattr(comfy.time, "sleep", lambda s: None)


# --- _render ----------------------------------------------------------------

def test_render_sustituye_texto_escapado_y_numericos_sin_comillas():
    crudo = json.dumps({"1": {"inputs": {"text": "{PROMPT}", "seed": "{SEED}"}}})
    wf = comfy._render(crudo, PROMPT='un "gato"\nnegro', SEED=42)
    assert wf["1"]["inputs"] == {"text": 'un "gato"\nnegro', "seed": 42}


def test_render_booleanos_y_flotantes_llegan_con_su_tipo():
    crudo = json.dumps({"1": {"inputs": {"a": "{FLAG}", "b": "{TEMP}"}}})
    wf = comfy._render(crudo, FLAG=True, TEMP=0.85)
    assert wf["1"]["inputs"] == {"a": True, "b": 0.85}


def test_render_placeholder_del_workflow_que_nadie_rellena():
    crudo = json.dumps({"1": {"inputs": {"a": "{PROMPT}", "b": "{OTRO}"}}})
    with pytest.raises(ComfyError, match="OTRO"):
        comfy._render(crudo, PROMPT="x")


def test_render_valor_que_no_esta_en_el_workflow_se_ignora():
    crudo = json.dumps({"1": {"inputs": {"a": "{PROMPT}"}}})
    assert comfy._render(crudo, PROMPT="x", SEED=1)["1"]["inputs"] == {"a": "x"}


def test_render_texto_vacio():
    crudo = json.dumps({"1": {"inputs": {"a": "{PROMPT}"}}})
    assert comfy._render(crudo, PROMPT="")["1"]["inputs"]["a"] == ""


def test_render_con_llaves_en_el_texto_no_falla():
    """Un prompt con dynamic prompts {a|b} no debe confundirse con placeholder."""
    crudo = json.dumps({"1": {"inputs": {"a": "{PROMPT}"}}})
    assert comfy._render(crudo, PROMPT="{rojo|azul}")["1"]["inputs"]["a"] == "{rojo|azul}"


# --- poda de referencias opcionales ----------------------------------------

def _grafo_con_referencias():
    return {
        "load1": {"inputs": {"image": "{IMAGE1}"}},
        "load2": {"inputs": {"image": "{IMAGE2}"}},
        "esc1": {"inputs": {"image": ["load1", 0]}},
        "esc2": {"inputs": {"image": ["load2", 0]}},
        "edit": {"inputs": {"prompt": "{PROMPT}", "i1": ["esc1", 0], "i2": ["esc2", 0]}},
    }


def test_nodos_de_encuentra_los_que_usan_el_placeholder():
    assert comfy._nodos_de(_grafo_con_referencias(), {"IMAGE2"}) == {"load2"}
    assert comfy._nodos_de(_grafo_con_referencias(), {"NADA"}) == set()


def test_render_con_referencia_ausente_poda_la_cadena_colgante():
    crudo = json.dumps(_grafo_con_referencias())
    wf = comfy._render(crudo, IMAGE1="a.png", IMAGE2=None, PROMPT="p")
    assert set(wf) == {"load1", "esc1", "edit"}
    assert wf["edit"]["inputs"] == {"prompt": "p", "i1": ["esc1", 0]}
    assert wf["load1"]["inputs"]["image"] == "a.png"


def test_podar_quita_el_nodo_consumidor_si_solo_vivia_de_los_muertos():
    g = {
        "a": {"inputs": {"x": "{A}"}},
        "b": {"inputs": {"x": ["a", 0]}},
        "c": {"inputs": {"y": ["b", 0]}},
    }
    comfy._podar(g, {"a"})
    assert g == {}


def test_podar_sin_muertos_no_cambia_nada():
    g = _grafo_con_referencias()
    copia = json.loads(json.dumps(g))
    comfy._podar(g, set())
    assert g == copia


# --- _error_legible ---------------------------------------------------------

def test_error_legible_extrae_el_execution_error():
    status = {"messages": [
        ["execution_start", {}],
        ["execution_error", {"node_type": "KSampler", "exception_message": "OOM  "}],
    ]}
    assert comfy._error_legible(status) == "[KSampler] OOM"


def test_error_legible_sin_mensajes_vuelca_el_status_truncado():
    texto = comfy._error_legible({"x": "y" * 1000})
    assert len(texto) == 300


# --- _encolar_y_esperar -----------------------------------------------------

def _servidor(historiales, prompt_status=200):
    """Handler de ComfyUI: /prompt devuelve un id; /history va sirviendo `historiales`."""
    pendientes = list(historiales)

    def handler(request):
        if request.url.path == "/prompt":
            if prompt_status >= 400:
                return httpx.Response(prompt_status, text="workflow roto")
            return httpx.Response(200, json={"prompt_id": "p1"})
        if request.url.path == "/history/p1":
            h = pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]
            return httpx.Response(200, json=h)
        return httpx.Response(404)

    return handler


def test_encolar_y_esperar_hace_polling_hasta_completar(http_mock):
    entry = {"status": {"completed": True}, "outputs": {}}
    vistas = http_mock(_servidor([{}, {"p1": {"status": {}}}, {"p1": entry}]))
    with httpx.Client() as c:
        assert comfy._encolar_y_esperar(c, {"1": {}}) == entry
    assert sum(v.url.path.startswith("/history") for v in vistas) == 3


def test_encolar_y_esperar_workflow_rechazado(http_mock):
    http_mock(_servidor([{}], prompt_status=400))
    with httpx.Client() as c, pytest.raises(ComfyError, match="rechazó"):
        comfy._encolar_y_esperar(c, {})


def test_encolar_y_esperar_error_de_ejecucion(http_mock):
    err = {"p1": {"status": {"status_str": "error", "messages": [
        ["execution_error", {"node_type": "VAEDecode", "exception_message": "boom"}]]}}}
    http_mock(_servidor([err]))
    with httpx.Client() as c, pytest.raises(ComfyError, match=r"\[VAEDecode\] boom"):
        comfy._encolar_y_esperar(c, {})


def test_encolar_y_esperar_timeout(http_mock, monkeypatch):
    monkeypatch.setattr(comfy, "TIMEOUT_S", -1)
    http_mock(_servidor([{}]))
    with httpx.Client() as c, pytest.raises(ComfyError, match="Timeout"):
        comfy._encolar_y_esperar(c, {})


# --- descargas --------------------------------------------------------------

def _view(contenido=b"datos", status=200):
    return lambda request: httpx.Response(status, content=contenido)


def test_descargar_imagen(http_mock, tmp_path):
    vistas = http_mock(_view(b"png"))
    entry = {"outputs": {"9": {"images": [{"filename": "a.png", "subfolder": "s"}]}}}
    destino = tmp_path / "out.png"
    with httpx.Client() as c:
        comfy._descargar_primera_imagen(c, entry, destino)
    assert destino.read_bytes() == b"png"
    assert vistas[0].url.params["filename"] == "a.png"
    assert vistas[0].url.params["subfolder"] == "s"


@pytest.mark.parametrize("entry", [{}, {"outputs": {}}, {"outputs": {"1": {"images": []}}}])
def test_descargar_imagen_sin_salida(http_mock, tmp_path, entry):
    http_mock(_view())
    with httpx.Client() as c, pytest.raises(ComfyError, match="sin imágenes"):
        comfy._descargar_primera_imagen(c, entry, tmp_path / "x.png")


def test_descargar_imagen_view_falla(http_mock, tmp_path):
    http_mock(_view(status=404))
    entry = {"outputs": {"1": {"images": [{"filename": "a.png"}]}}}
    with httpx.Client() as c, pytest.raises(ComfyError, match="No se pudo descargar"):
        comfy._descargar_primera_imagen(c, entry, tmp_path / "x.png")


def test_descargar_video_prefiere_extension_de_video(http_mock, tmp_path):
    vistas = http_mock(_view(b"mp4"))
    entry = {"outputs": {"1": {"gifs": [{"filename": "preview.png"}, {"filename": "clip.MP4"}]}}}
    destino = tmp_path / "v.mp4"
    with httpx.Client() as c:
        comfy._descargar_primer_video(c, entry, destino)
    assert vistas[0].url.params["filename"] == "clip.MP4"
    assert destino.read_bytes() == b"mp4"


def test_descargar_video_sin_archivos(http_mock, tmp_path):
    http_mock(_view())
    with httpx.Client() as c, pytest.raises(ComfyError, match="sin producir un archivo de video"):
        comfy._descargar_primer_video(c, {"outputs": {"1": {"x": "no-lista"}}}, tmp_path / "v.mp4")


def test_descargar_audio_conserva_la_extension_de_origen(http_mock, tmp_path):
    http_mock(_view(b"mp3"))
    entry = {"outputs": {"1": {"audio": [{"filename": "pista.mp3"}]}}}
    with httpx.Client() as c:
        final = comfy._descargar_primer_audio(c, entry, tmp_path / "pista.flac")
    assert final == tmp_path / "pista.mp3" and final.read_bytes() == b"mp3"


def test_descargar_audio_sin_archivos(http_mock, tmp_path):
    http_mock(_view())
    with httpx.Client() as c, pytest.raises(ComfyError, match="sin producir un archivo de audio"):
        comfy._descargar_primer_audio(c, {"outputs": {}}, tmp_path / "p.flac")


def test_subir_imagen(http_mock, tmp_path):
    http_mock(lambda r: httpx.Response(200, json={"name": "subida.png"}))
    origen = tmp_path / "a.png"
    origen.write_bytes(b"png")
    with httpx.Client() as c:
        assert comfy._subir_imagen(c, origen) == "subida.png"


def test_subir_imagen_rechazada(http_mock, tmp_path):
    http_mock(lambda r: httpx.Response(500, text="disco lleno"))
    origen = tmp_path / "a.png"
    origen.write_bytes(b"png")
    with httpx.Client() as c, pytest.raises(ComfyError, match="No se pudo subir"):
        comfy._subir_imagen(c, origen)


# --- _workflow_motor --------------------------------------------------------

def test_workflow_motor_desconocido():
    with pytest.raises(ComfyError, match="desconocido"):
        comfy._workflow_motor("no_existe", "generar")


def test_workflow_motor_que_no_sabe_ese_modo(monkeypatch):
    from backend.config import MotorImagen

    motor = MotorImagen(id="solo_gen", nombre="Solo gen", generar="x.json", editar=None)
    monkeypatch.setitem(comfy.IMAGEN_MOTORES, "solo_gen", motor)
    with pytest.raises(ComfyError, match="no sabe editar"):
        comfy._workflow_motor("solo_gen", "editar")


def test_workflow_motor_con_archivo_inexistente(monkeypatch):
    from backend.config import MotorImagen

    motor = MotorImagen(id="roto", nombre="Roto", generar="workflows/no_hay.json", editar=None)
    monkeypatch.setitem(comfy.IMAGEN_MOTORES, "roto", motor)
    with pytest.raises(ComfyError, match="No existe el workflow"):
        comfy._workflow_motor("roto", "generar")


def test_workflow_motor_por_defecto_existe():
    assert comfy._workflow_motor(None, "generar").exists()
    assert comfy._workflow_motor(None, "editar").exists()


# --- funciones públicas, de punta a punta con ComfyUI simulado -------------

def _comfy_completo(salida: dict, contenido=b"bytes"):
    def handler(request):
        p = request.url.path
        if p == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p1"})
        if p == "/history/p1":
            return httpx.Response(200, json={"p1": {"status": {"completed": True}, "outputs": salida}})
        if p == "/upload/image":
            return httpx.Response(200, json={"name": "subida.png"})
        if p == "/view":
            return httpx.Response(200, content=contenido)
        return httpx.Response(404)

    return handler


def test_generar_imagen_de_punta_a_punta(http_mock, tmp_path, monkeypatch):
    wf = tmp_path / "wf.json"
    wf.write_text(json.dumps({"1": {"inputs": {
        "p": "{PROMPT}", "s": "{SEED}", "w": "{WIDTH}", "h": "{HEIGHT}"}}}))
    monkeypatch.setattr(comfy, "_workflow_motor", lambda motor, modo: wf)
    vistas = http_mock(_comfy_completo({"9": {"images": [{"filename": "r.png"}]}}, b"IMG"))
    destino = tmp_path / "salida.png"

    comfy.generar_imagen("un gato", 7, destino, width=512, height=768)

    assert destino.read_bytes() == b"IMG"
    enviado = json.loads(next(v for v in vistas if v.url.path == "/prompt").content)
    assert enviado["prompt"]["1"]["inputs"] == {"p": "un gato", "s": 7, "w": 512, "h": 768}


def test_generar_imagen_propaga_el_error_de_comfy(http_mock, tmp_path, monkeypatch):
    wf = tmp_path / "wf.json"
    wf.write_text(json.dumps({"1": {"inputs": {}}}))
    monkeypatch.setattr(comfy, "_workflow_motor", lambda motor, modo: wf)
    http_mock(lambda r: httpx.Response(400, text="no"))
    with pytest.raises(ComfyError):
        comfy.generar_imagen("x", 1, tmp_path / "o.png")


def test_upscale_imagen_sube_el_origen_y_descarga(http_mock, tmp_path):
    vistas = http_mock(_comfy_completo({"9": {"images": [{"filename": "up.png"}]}}, b"GRANDE"))
    origen = tmp_path / "o.png"
    origen.write_bytes(b"png")
    destino = tmp_path / "d.png"

    comfy.upscale_imagen(origen, destino)

    assert destino.read_bytes() == b"GRANDE"
    assert [v.url.path for v in vistas][0] == "/upload/image"


def test_generar_video_i2v_sin_workflow_da_error_claro(tmp_path, monkeypatch):
    from backend.config import MotorI2V

    monkeypatch.setattr(
        comfy, "motor_i2v",
        lambda _=None: MotorI2V(id="roto", nombre="Roto",
                                workflow="no/existe.json", frames=21, fps_origen=24),
    )
    with pytest.raises(ComfyError, match="No existe el workflow del motor i2v 'roto'"):
        comfy.generar_video_i2v(tmp_path / "a.png", "p", 1, tmp_path / "v.mp4")


def test_generar_video_i2v_usa_los_cuadros_del_motor(tmp_path, monkeypatch):
    """Los cuadros los pone el motor, no quien llama: cada modelo admite su
    forma y pedirle los de otro sale caro o falla."""
    from backend.config import MotorI2V

    wf = tmp_path / "wf.json"
    wf.write_text('{"n": {"class_type": "X", "inputs": {"f": "{FRAMES}", '
                  '"i": "{IMAGE}", "p": "{PROMPT}", "s": "{SEED}"}}}')
    monkeypatch.setattr(
        comfy, "motor_i2v",
        lambda _=None: MotorI2V(id="m", nombre="M", workflow=str(wf.relative_to(comfy.ROOT))
                                if str(wf).startswith(str(comfy.ROOT)) else str(wf),
                                frames=17, fps_origen=24),
    )
    enviados = {}
    monkeypatch.setattr(comfy, "_subir_imagen", lambda c, p: "img.png")
    monkeypatch.setattr(comfy, "_encolar_y_esperar",
                        lambda c, wf: enviados.update(wf) or {"outputs": {}})
    monkeypatch.setattr(comfy, "_descargar_primer_video", lambda c, e, d: None)

    comfy.generar_video_i2v(tmp_path / "a.png", "p", 1, tmp_path / "v.mp4")
    assert enviados["n"]["inputs"]["f"] == 17


def test_generar_musica_sin_workflow_da_error_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(comfy, "MUSICA_WORKFLOW", "no/existe.json")
    with pytest.raises(ComfyError, match="No existe el workflow de música"):
        comfy.generar_musica("t", "", 1, 30, 120, "C major", "4", "es", tmp_path / "m.flac")


def test_generar_musica_traduce_el_bug_de_multinomial_en_metal(http_mock, tmp_path):
    err = {"p1": {"status": {"status_str": "error", "messages": [
        ["execution_error", {"node_type": "X", "exception_message": "index out of bounds"}]]}}}
    http_mock(_servidor([err]))
    with pytest.raises(ComfyError, match="multinomial"):
        comfy.generar_musica("t", "", 1, 30, 120, "C major", "4", "es",
                             tmp_path / "m.flac", lm_temperature=0.85, lm_device="default")


def test_generar_musica_en_cpu_no_traduce_el_error(http_mock, tmp_path):
    err = {"p1": {"status": {"status_str": "error", "messages": [
        ["execution_error", {"node_type": "X", "exception_message": "index out of bounds"}]]}}}
    http_mock(_servidor([err]))
    with pytest.raises(ComfyError, match="out of bounds") as e:
        comfy.generar_musica("t", "", 1, 30, 120, "C major", "4", "es",
                             tmp_path / "m.flac", lm_device="cpu")
    assert "multinomial" not in str(e.value)


# --- memoria ----------------------------------------------------------------

@pytest.fixture
def reloj(monkeypatch):
    """Reloj falso que avanza un segundo por consulta.

    Con `sin_esperas` anulando el sleep y `time.monotonic` de verdad, una espera
    que no se cumple daría vueltas los 20 s reales de `espera_liberacion_s`.
    """
    tic = iter(range(0, 10_000))
    monkeypatch.setattr(comfy.time, "monotonic", lambda: next(tic))


def _comfy_ok(request):
    """ComfyUI que atiende el /free sin decir nada más."""
    return httpx.Response(200)


def _memoria(monkeypatch, libres):
    """La memoria disponible del sistema devuelve `libres[i]` GiB en la i-ésima
    lectura; el último valor se repite.

    Ya no se simula con `/system_stats`: la medición salió de ComfyUI a
    `backend/memoria.py` para no depender de que esté escuchando, que es justo
    cuando hace falta. El último valor se repite para que un test pueda decir
    "sube al tercer sondeo y se queda ahí" sin contar los sondeos.
    """
    lecturas = {"n": 0}

    def disponible():
        i = min(lecturas["n"], len(libres) - 1)
        lecturas["n"] += 1
        return libres[i]

    monkeypatch.setattr(comfy.memoria, "disponible_gb", disponible)
    return lecturas


def test_memoria_libre_sale_de_la_del_sistema(monkeypatch):
    _memoria(monkeypatch, [30.0])
    assert comfy.memoria_libre_gb() == pytest.approx(30.0)


def test_memoria_libre_sin_medicion_es_none(monkeypatch):
    monkeypatch.setattr(comfy.memoria, "disponible_gb", lambda: None)
    assert comfy.memoria_libre_gb() is None


def test_liberar_memoria_pide_descargar_modelos(http_mock, monkeypatch):
    _memoria(monkeypatch, [30.0])
    vistas = http_mock(_comfy_ok)
    comfy.liberar_memoria()
    free = [v for v in vistas if v.url.path == "/free"]
    assert len(free) == 1
    assert json.loads(free[0].content) == {"unload_models": True, "free_memory": True}


def test_liberar_memoria_sin_comfy_no_espera_una_descarga_que_nadie_hara(
    http_mock, monkeypatch, reloj
):
    """ComfyUI cerrado: nadie recogió la bandera, así que no hay descarga en
    camino y esperar los 20 s de rigor no cambiaría nada. La memoria que falte
    la tiene otra cosa, y eso lo dirá el mensaje de quien llama."""
    _memoria(monkeypatch, [9.6])

    def handler(request):
        raise httpx.ConnectError("caído")

    http_mock(handler)
    lib = comfy.liberar_memoria(hasta_gb=22)
    assert lib.peticiones == 0 and lib.espera_s == 0 and not lib.logrado
    assert lib.antes_gb == pytest.approx(9.6)


def test_liberar_memoria_sin_comfy_pero_con_sitio_de_sobra(
    http_mock, monkeypatch, reloj
):
    _memoria(monkeypatch, [39.2])

    def handler(request):
        raise httpx.ConnectError("caído")

    http_mock(handler)
    assert comfy.liberar_memoria(hasta_gb=22).logrado


def test_liberar_memoria_sin_medicion_no_se_da_por_fallida(http_mock, monkeypatch):
    monkeypatch.setattr(comfy.memoria, "disponible_gb", lambda: None)
    http_mock(_comfy_ok)
    lib = comfy.liberar_memoria(hasta_gb=22)
    assert lib.logrado and lib.antes_gb is None


def test_liberar_memoria_sin_hasta_gb_no_espera(http_mock, monkeypatch):
    """Lo que hacen las etapas al terminar: sueltan para el siguiente y siguen."""
    _memoria(monkeypatch, [16.0])
    http_mock(_comfy_ok)
    lib = comfy.liberar_memoria()
    assert lib.logrado and lib.espera_s == 0 and lib.antes_gb == pytest.approx(16.0)


def test_liberar_memoria_si_ya_sobra_no_espera(http_mock, monkeypatch, reloj):
    """ComfyUI sin nada cargado: no hay ninguna bajada que esperar."""
    _memoria(monkeypatch, [27.0])
    http_mock(_comfy_ok)
    lib = comfy.liberar_memoria(hasta_gb=22)
    assert lib.logrado and lib.peticiones == 1 and lib.espera_s <= 1


def test_liberar_memoria_espera_a_ver_la_bajada(http_mock, monkeypatch, reloj):
    _memoria(monkeypatch, [16.0, 16.0, 10.0, 27.0])
    http_mock(_comfy_ok)
    lib = comfy.liberar_memoria(hasta_gb=22)
    assert lib.logrado
    assert lib.antes_gb == pytest.approx(16.0) and lib.despues_gb == pytest.approx(27.0)


def test_liberar_memoria_no_se_fia_del_bajon_intermedio(http_mock, monkeypatch, reloj):
    """Descargar mueve los pesos al dispositivo de offload y un instante hay dos
    copias en la misma memoria unificada: medido, baja de 16,4 a 10,0 GiB antes
    de subir. Quedarse en ese bajón no cuenta como memoria libre."""
    _memoria(monkeypatch, [16.4, 10.0])
    http_mock(_comfy_ok)
    lib = comfy.liberar_memoria(hasta_gb=22)
    assert not lib.logrado and lib.despues_gb == pytest.approx(10.0)


def test_liberar_memoria_repite_el_free_si_no_baja(http_mock, monkeypatch, reloj):
    """La bandera se consume entre prompts: la primera pudo gastarse en uno que
    ya estaba en vuelo, así que se vuelve a pedir una vez."""
    _memoria(monkeypatch, [16.0])
    vistas = http_mock(_comfy_ok)
    lib = comfy.liberar_memoria(hasta_gb=22)
    assert not lib.logrado and lib.peticiones == 2
    assert len([v for v in vistas if v.url.path == "/free"]) == 2


def test_liberar_memoria_si_la_medicion_se_cae_a_mitad_no_bloquea(
    http_mock, monkeypatch, reloj
):
    """Deja de poder medirse mientras se espera: no hay con qué decir que no
    soltó, así que no se bloquea a quien espera."""
    lecturas = {"n": 0}

    def disponible():
        lecturas["n"] += 1
        return 16.0 if lecturas["n"] == 1 else None

    monkeypatch.setattr(comfy.memoria, "disponible_gb", disponible)
    http_mock(_comfy_ok)
    lib = comfy.liberar_memoria(hasta_gb=22)
    assert lib.logrado and lib.despues_gb is None
    assert "dejó de responder" in str(lib)


def test_liberacion_se_cuenta_sola_en_una_linea():
    lib = comfy.Liberacion(16.4, 27.0, 1.7, 1, True)
    assert str(lib) == "16.4 → 27.0 GiB libres (+10.6 en 1.7 s, 1 petición a /free)"

    dos = comfy.Liberacion(16.4, 16.4, 20.0, 2, False)
    assert "2 peticiones a /free" in str(dos)


def test_el_workflow_de_musica_decodifica_por_trozos(tmp_path, monkeypatch):
    """El workflow de verdad del repo, no uno de prueba: que decodifique por
    trozos es la diferencia entre 14 GiB de swap y ninguno.

    De una pasada, el último paso del decoder pide `128 × duración × 48000 × 2`
    bytes en un solo tensor (3,43 GiB para 300 s) encima de los 19 GiB de
    modelos que ComfyUI no suelta con `--gpu-only`. Un cambio de nodo en el
    workflow lo devolvería sin que falle nada más, así que se fija aquí.
    """
    enviados = {}
    monkeypatch.setattr(comfy, "_encolar_y_esperar",
                        lambda c, wf: enviados.update(wf) or {"outputs": {}})
    monkeypatch.setattr(comfy, "_descargar_primer_audio", lambda c, e, d: d)

    comfy.generar_musica("t", "", 1, 300, 120, "C major", "4", "es",
                         tmp_path / "m.flac", tile_size=1024, overlap=128)

    tiled = [n for n in enviados.values() if n["class_type"] == "VAEDecodeAudioTiled"]
    assert len(tiled) == 1, "el workflow de música no decodifica el audio por trozos"
    assert tiled[0]["inputs"]["tile_size"] == 1024
    assert tiled[0]["inputs"]["overlap"] == 128
    assert not any(n["class_type"] == "VAEDecodeAudio" for n in enviados.values())
