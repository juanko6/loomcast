"""La cola de verdad (`queue.encolar` + `_procesar`), con handlers de mentira."""
import pytest

from backend import parada
from backend.clients import comfy
from backend.repositories import jobs as jobs_repo
from backend.services import cancelacion
from backend.workers import queue

pytestmark = pytest.mark.integration


@pytest.fixture
def cola(engine, monkeypatch):
    """Cola real sobre la BD temporal, sin llama-server y con handlers sustituibles.

    Los reintentos van sin espera: lo que se prueba es que los haya y cuántos,
    no que duerma 20 s. Y la parada no habla con ComfyUI.
    """
    from backend.services import llm_runtime

    llamadas = []
    monkeypatch.setattr(llm_runtime, "liberar", lambda motivo: llamadas.append(("liberar", motivo)))
    # «Sin llama-server» también por arriba: `asegurar` mide la memoria y lanza
    # el proceso, y lo que estos tests prueban es la cola, no eso.
    monkeypatch.setattr(llm_runtime, "asegurar", lambda: llamadas.append(("asegurar",)))
    monkeypatch.setattr(queue, "HANDLERS", dict(queue.HANDLERS))
    monkeypatch.setattr(queue, "ESPERA_BASE_S", 0)
    monkeypatch.setattr(cancelacion.comfy, "interrumpir", lambda: llamadas.append(("interrumpir",)))
    while not queue._cola.empty():
        queue._cola.get_nowait()
    yield llamadas
    parada.limpiar()
    while not queue._cola.empty():
        queue._cola.get_nowait()


def _estado(job_id):
    from backend.db import get_session

    with get_session() as s:
        j = jobs_repo.obtener(s, job_id)
        return j.estado, j.log


def _job(job_id):
    from backend.db import get_session

    with get_session() as s:
        return jobs_repo.obtener(s, job_id)


def _comfy_caido(intentos):
    """Handler que siempre falla con el fallo transitorio más habitual."""

    def handler(ref):
        intentos.append(ref)
        raise comfy.ComfyError("ComfyUI no responde")

    return handler


def test_encolar_tipo_desconocido(cola):
    with pytest.raises(ValueError, match="desconocido"):
        queue.encolar("no_existe", 1)


def test_job_ok_pasa_params_como_kwargs_y_guarda_log(cola):
    recibido = {}
    queue.HANDLERS["generar_clips"] = lambda ref, **kw: recibido.update(ref=ref, **kw) or "hecho"
    queue.HANDLERS["armar_video"] = lambda ref, **kw: "armado"
    jid = queue.encolar("generar_clips", 7, orden=3)

    queue._procesar(queue._tomar())

    assert recibido == {"ref": 7, "orden": 3}
    assert _estado(jid) == ("ok", "hecho")
    # Etapa de GPU: se descarga el LLM antes de empezar.
    assert cola == [("liberar", "empieza generar_clips")]


def test_job_con_excepcion_queda_en_error_y_no_encadena(cola):
    def roto(ref):
        raise RuntimeError("boom")

    queue.HANDLERS["generar_clips"] = roto
    jid = queue.encolar("generar_clips", 1)

    queue._procesar(queue._tomar())

    estado, log = _estado(jid)
    assert estado == "error" and "boom" in log
    assert queue._cola.empty()


def test_job_ok_encadena_el_siguiente(cola):
    queue.HANDLERS["generar_clips"] = lambda ref: "ok"
    jid = queue.encolar("generar_clips", 5)

    queue._procesar(queue._tomar())

    siguiente = queue._tomar()
    assert siguiente != jid
    from backend.db import get_session

    with get_session() as s:
        j = jobs_repo.obtener(s, siguiente)
        assert (j.tipo, j.ref_id) == ("armar_video", 5)


def test_job_de_llm_usa_en_uso_y_no_libera(cola, monkeypatch):
    from backend.services import llm_runtime
    import contextlib

    entradas = []

    @contextlib.contextmanager
    def en_uso():
        entradas.append("entra")
        yield

    monkeypatch.setattr(llm_runtime, "en_uso", en_uso)
    queue.HANDLERS["generar_ideas"] = lambda ref: "ideas"
    jid = queue.encolar("generar_ideas", 1)

    queue._procesar(queue._tomar())

    assert entradas == ["entra"] and cola == []
    assert _estado(jid) == ("ok", "ideas")


# --- reintentos -------------------------------------------------------------

def test_fallo_transitorio_se_reintenta_hasta_el_tope_y_acaba_en_error(cola, session):
    """Tres intentos, estado final "error" y la cuenta guardada en el job."""
    from tests import factories as f

    p = f.proyecto(session)
    intentos = []
    queue.HANDLERS["generar_imagenes"] = _comfy_caido(intentos)
    jid = queue.encolar("generar_imagenes", p.id)

    queue._procesar(queue._tomar())

    assert len(intentos) == queue.INTENTOS == 3
    estado, log = _estado(jid)
    assert estado == "error"
    assert "Falló 3 veces" in log and "ComfyUI no responde" in log
    assert _job(jid).intentos == 3


def test_fallo_de_validacion_no_se_reintenta(cola, session):
    """Falta una entrada: repetir daría el mismo error (los ValueError de las etapas)."""
    from tests import factories as f

    p = f.proyecto(session)
    intentos = []

    def sin_escenas(ref):
        intentos.append(ref)
        raise ValueError("El proyecto no tiene escenas; genera las escenas primero")

    queue.HANDLERS["generar_imagenes"] = sin_escenas
    jid = queue.encolar("generar_imagenes", p.id)

    queue._procesar(queue._tomar())

    assert len(intentos) == 1
    estado, log = _estado(jid)
    assert estado == "error" and "no tiene escenas" in log
    assert "Falló" not in log and _job(jid).intentos == 1


def test_un_archivo_que_falta_no_se_reintenta(cola, session):
    """FileNotFoundError es un OSError, pero no se arregla repitiendo."""
    from tests import factories as f

    p = f.proyecto(session)
    intentos = []

    def sin_ffmpeg(ref):
        intentos.append(ref)
        raise FileNotFoundError(2, "No such file or directory: 'ffmpeg'")

    queue.HANDLERS["armar_video"] = sin_ffmpeg
    jid = queue.encolar("armar_video", p.id)

    queue._procesar(queue._tomar())

    assert len(intentos) == 1 and _estado(jid)[0] == "error"


def test_la_cadena_sale_una_sola_vez_y_tras_el_intento_bueno(cola, session):
    from tests import factories as f

    p = f.proyecto(session)
    intentos = []

    def a_la_tercera(ref):
        intentos.append(ref)
        if len(intentos) < 3:
            raise comfy.ComfyError("ComfyUI arrancando")
        return "clips hechos"

    queue.HANDLERS["generar_clips"] = a_la_tercera
    jid = queue.encolar("generar_clips", p.id)

    queue._procesar(queue._tomar())

    assert len(intentos) == 3
    assert _estado(jid) == ("ok", "clips hechos")
    assert _job(jid).intentos == 3
    siguiente = queue._tomar()
    assert _job(siguiente).tipo == "armar_video"
    assert queue._cola.empty()          # una sola vez, no una por intento


def test_no_se_reintenta_si_el_proyecto_ya_no_existe(cola):
    """El reintento daría otro error, y el que vale es el primero."""
    intentos = []
    queue.HANDLERS["generar_imagenes"] = _comfy_caido(intentos)
    jid = queue.encolar("generar_imagenes", 999)

    queue._procesar(queue._tomar())

    assert len(intentos) == 1
    estado, log = _estado(jid)
    assert estado == "error" and "ya no existe" in log


def test_la_espera_entre_intentos_crece(cola, session, monkeypatch):
    from tests import factories as f

    p = f.proyecto(session)
    esperas = []
    monkeypatch.setattr(queue, "ESPERA_BASE_S", 20)
    monkeypatch.setattr(queue, "_esperar", lambda s: esperas.append(s) or True)
    queue.HANDLERS["generar_imagenes"] = _comfy_caido([])
    queue.encolar("generar_imagenes", p.id)

    queue._procesar(queue._tomar())

    assert esperas == [20, 40]          # la última vez ya no espera: no reintenta


# --- parada -----------------------------------------------------------------

def test_un_job_cancelado_mientras_esperaba_se_salta(cola, session):
    from backend.db import get_session

    llamado = []
    queue.HANDLERS["generar_imagenes"] = lambda ref: llamado.append(ref)
    jid = queue.encolar("generar_imagenes", 1)
    with get_session() as s:
        jobs_repo.cancelar(s, jobs_repo.obtener(s, jid), "Parado desde la interfaz")
        s.commit()

    queue._procesar(queue._tomar())

    assert llamado == []
    assert _estado(jid) == ("cancelado", "Parado desde la interfaz")


def test_parar_el_job_en_curso_lo_corta_y_no_encadena(cola, session):
    """El handler se para entre elemento y elemento, como los lotes de verdad."""
    from backend.services import jobs as jobs_service
    from tests import factories as f

    p = f.proyecto(session)
    hechos = []

    def lote(ref):
        for i in range(5):
            # Lo que haría la UI a mitad del lote.
            if i == 2:
                jobs_service.parar()
            parada.comprobar(f"quedaban {5 - i} clips")
            hechos.append(i)
        return "cinco clips"

    queue.HANDLERS["generar_clips"] = lote
    jid = queue.encolar("generar_clips", p.id)

    queue._procesar(queue._tomar())

    assert hechos == [0, 1]             # lo ya hecho se queda hecho
    estado, log = _estado(jid)
    assert estado == "cancelado" and "quedaban 3 clips" in log
    assert queue._cola.empty()          # no encadena armar_video
    assert ("interrumpir",) in cola     # y se le pidió a ComfyUI que pare


def test_un_fallo_provocado_por_la_parada_cuenta_como_cancelado(cola, session):
    """ComfyUI interrumpido o un ffmpeg al que matamos sube como error: no lo es."""
    from backend.services import jobs as jobs_service
    from tests import factories as f

    p = f.proyecto(session)
    intentos = []

    def cortado(ref):
        intentos.append(ref)
        jobs_service.parar()
        raise comfy.ComfyError("Timeout esperando el workflow")

    queue.HANDLERS["generar_imagenes"] = cortado
    jid = queue.encolar("generar_imagenes", p.id)

    queue._procesar(queue._tomar())

    assert len(intentos) == 1           # tampoco se reintenta
    estado, log = _estado(jid)
    assert estado == "cancelado" and "Parado a petición del usuario" in log


def test_un_job_que_termina_justo_antes_del_corte_no_encadena(cola, session):
    from backend.services import jobs as jobs_service
    from tests import factories as f

    p = f.proyecto(session)

    def termina_y_para(ref):
        jobs_service.parar()
        return "clips hechos"

    queue.HANDLERS["generar_clips"] = termina_y_para
    jid = queue.encolar("generar_clips", p.id)

    queue._procesar(queue._tomar())

    assert _estado(jid)[0] == "ok"      # el trabajo está hecho y se dice
    assert queue._cola.empty()          # pero la etapa siguiente no sale


# --- apuntes de las capas de debajo -----------------------------------------

def test_el_log_del_job_recoge_los_apuntes(cola):
    """Lo que midió una capa que no escribe el log: la memoria que soltó ComfyUI
    antes de cargar el LLM. El historial de la UI es donde se lee."""
    from backend.services import apuntes

    def handler(ref):
        apuntes.anotar("Memoria para «X» (22 GiB): 16.4 → 27.0 GiB libres")
        return "ideas generadas"

    queue.HANDLERS["generar_ideas"] = handler
    jid = queue.encolar("generar_ideas", 1)

    queue._procesar(queue._tomar())

    estado, log = _estado(jid)
    assert estado == "ok"
    assert log == (
        "ideas generadas\n\nMemoria para «X» (22 GiB): 16.4 → 27.0 GiB libres"
    )


def test_los_apuntes_no_se_arrastran_al_job_siguiente(cola):
    from backend.services import apuntes

    def anota(ref):
        apuntes.anotar("algo del primero")
        return "hecho"

    queue.HANDLERS["generar_ideas"] = anota
    queue.HANDLERS["generar_guion"] = lambda ref: "guion"
    primero = queue.encolar("generar_ideas", 1)
    segundo = queue.encolar("generar_guion", 1)

    queue._procesar(queue._tomar())
    queue._procesar(queue._tomar())

    assert "algo del primero" in _estado(primero)[1]
    assert _estado(segundo) == ("ok", "guion")


# --- memoria antes de cargar un modelo dentro del backend -------------------
# La otra mitad del error que ya estaba arreglado por el lado del LLM: el
# `/free` con el que una etapa de ComfyUI suelta al terminar es a ciegas (vuelve
# en 1 ms con los pesos todavía dentro), así que la etapa de voz cargaba el TTS
# sobre una memoria que nadie había liberado.

def _mide(monkeypatch, antes=16.4, despues=27.0):
    pedido = []

    def liberar_memoria(hasta_gb=None):
        pedido.append(hasta_gb)
        return comfy.Liberacion(antes, despues, 1.7, 1, True)

    monkeypatch.setattr(queue.comfy, "liberar_memoria", liberar_memoria)
    return pedido


def test_una_etapa_que_carga_su_modelo_espera_la_memoria(cola, monkeypatch):
    pedido = _mide(monkeypatch)
    queue.HANDLERS["generar_voz"] = lambda ref: "voz lista"
    jid = queue.encolar("generar_voz", 1)

    queue._procesar(queue._tomar())

    assert pedido == [queue.COLA_MEMORIA_MODELO_GB]
    estado, log = _estado(jid)
    # Y la medición queda en el historial: es lo que hace falta leer el día que
    # una narración de 77 s tarda cinco minutos.
    assert estado == "ok" and "16.4 → 27.0" in log


def test_si_la_memoria_no_llega_la_etapa_de_voz_corre_igual(cola, monkeypatch):
    """Al contrario que el LLM, que se niega: allí lo que venía detrás eran
    22 GiB y arrancarlos a ciegas mataba al backend. Aquí son 4, que caben casi
    siempre, y negarse no los haría caber."""
    monkeypatch.setattr(
        queue.comfy,
        "liberar_memoria",
        lambda hasta_gb=None: comfy.Liberacion(6.0, 6.0, 20.0, 2, False),
    )
    queue.HANDLERS["generar_voz"] = lambda ref: "voz lista"
    jid = queue.encolar("generar_voz", 1)

    queue._procesar(queue._tomar())

    estado, log = _estado(jid)
    assert estado == "ok" and "6.0 → 6.0" in log


def test_la_musica_espera_la_memoria_de_ace_step(cola, monkeypatch):
    """El agujero del 2026-11-05. Los jobs de ComfyUI no pasaban por esta
    puerta porque su inquilino mayor era Z-Image (11,5 GiB) y colaba; ACE-Step
    son 18,5 y cargó sobre el llama-server que el kernel aún no había
    reclamado."""
    pedido = _mide(monkeypatch)
    queue.HANDLERS["generar_musica"] = lambda ref: "pista"
    jid = queue.encolar("generar_musica", 1)

    queue._procesar(queue._tomar())

    assert pedido == [queue.MUSICA_MEMORIA_GB]
    estado, log = _estado(jid)
    assert estado == "ok" and "16.4 → 27.0" in log


def test_la_portada_encadenada_tambien_espera(cola, monkeypatch):
    """La otra mitad: la portada sale detrás de la pista y cargaba su motor de
    imagen con los 18,5 GiB de ACE-Step todavía dentro de ComfyUI, porque el
    `/free` que manda la música al terminar vuelve en 1 ms sin comprobar nada."""
    pedido = _mide(monkeypatch)
    queue.HANDLERS["generar_musica"] = lambda ref: "pista"
    queue.HANDLERS["generar_portada_musica"] = lambda ref: "portada"
    queue.encolar("generar_musica", 1)

    queue._procesar(queue._tomar())  # la pista
    queue._procesar(queue._tomar())  # la portada, que encadena

    assert pedido == [queue.MUSICA_MEMORIA_GB, queue.IMAGEN_MEMORIA_GB]


def test_una_etapa_que_no_carga_nada_no_espera_memoria(cola, monkeypatch):
    """El armado es ffmpeg: esperar memoria ahí solo metería una espera y una
    nota en el historial de un job que no carga ningún modelo."""
    monkeypatch.setattr(
        queue.comfy,
        "liberar_memoria",
        lambda hasta_gb=None: pytest.fail("el armado no carga ningún modelo"),
    )
    queue.HANDLERS["armar_video"] = lambda ref: "armado"
    queue.encolar("armar_video", 1)

    queue._procesar(queue._tomar())


def test_el_swap_de_una_etapa_queda_en_su_historial(cola, monkeypatch):
    """Lo que no se ve de ninguna otra forma: al terminar, la memoria vuelve a
    parecer sana y el único rastro de que el equipo ha estado paginando es el
    contador."""
    _mide(monkeypatch)
    lecturas = iter([100.0, 115.3])
    monkeypatch.setattr(queue.memoria, "swapouts_gb", lambda: next(lecturas))
    queue.HANDLERS["generar_musica"] = lambda ref: "pista"
    jid = queue.encolar("generar_musica", 1)

    queue._procesar(queue._tomar())

    estado, log = _estado(jid)
    assert estado == "ok" and "15.3 GiB al swap" in log


def test_un_swap_de_nada_no_se_anota(cola, monkeypatch):
    """El sistema pagina un poco por su cuenta y un historial que avise de
    80 MiB en cada job no se lee."""
    _mide(monkeypatch)
    lecturas = iter([100.0, 100.08])
    monkeypatch.setattr(queue.memoria, "swapouts_gb", lambda: next(lecturas))
    queue.HANDLERS["generar_musica"] = lambda ref: "pista"
    jid = queue.encolar("generar_musica", 1)

    queue._procesar(queue._tomar())

    assert "swap" not in _estado(jid)[1]


def test_una_etapa_de_texto_no_pasa_por_esa_puerta(cola, monkeypatch):
    """El LLM tiene la suya, y pide los GiB que declare su modelo."""
    monkeypatch.setattr(
        queue.comfy,
        "liberar_memoria",
        lambda hasta_gb=None: pytest.fail("esa puerta no era para el LLM"),
    )
    queue.HANDLERS["generar_ideas"] = lambda ref: "ideas"
    queue.encolar("generar_ideas", 1)

    queue._procesar(queue._tomar())


def test_en_un_fallo_las_notas_van_delante_del_error(cola):
    """El motivo que escribe el autopiloto es la última línea del log
    (`autopiloto._resumen`), así que con las notas detrás el motivo de una
    etapa caída pasó a ser la medición de memoria en vez del error."""
    from backend.services import apuntes

    def handler(ref):
        apuntes.anotar("Memoria para generar_voz (8 GiB): 16.4 → 27.0 GiB libres")
        raise ValueError("El proyecto no tiene escenas")

    queue.HANDLERS["generar_ideas"] = handler
    jid = queue.encolar("generar_ideas", 1)

    queue._procesar(queue._tomar())

    estado, log = _estado(jid)
    lineas = [x for x in log.splitlines() if x.strip()]
    assert estado == "error"
    assert lineas[0].startswith("Memoria para")
    assert "no tiene escenas" in lineas[-1]
