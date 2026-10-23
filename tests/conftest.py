"""Fixtures comunes. Ningún test toca loomcast.db, ComfyUI, el LLM ni la GPU."""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import db as db_mod
from backend.models import Base


@pytest.fixture
def engine(monkeypatch):
    """SQLite en memoria que sustituye al engine global de backend.db.

    `get_session` y `_migrar` resuelven `SessionLocal`/`engine` en el módulo
    `db` en cada llamada, así que basta con parchearlos ahí. StaticPool + sin
    check_same_thread: la API y el worker usan hilos distintos.
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(db_mod, "engine", eng)
    monkeypatch.setattr(
        db_mod, "SessionLocal", sessionmaker(bind=eng, expire_on_commit=False)
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with db_mod.get_session() as s:
        yield s


@pytest.fixture
def jobs_encolados(monkeypatch):
    """Sustituye la cola: registra (tipo, ref_id) en vez de crear jobs y despertar al worker."""
    from backend.workers import queue

    class Llamadas(list):
        # Los kwargs (params del job) por separado, para no ensuciar las
        # comparaciones de los tests que solo miran (tipo, ref_id). La prioridad
        # va aparte de los params porque no es un kwarg del handler: es el sitio
        # que ocupa el job en la cola.
        params: list[dict]
        prioridades: list[int]

    llamadas = Llamadas()
    llamadas.params = []
    llamadas.prioridades = []

    def falso(tipo, ref_id, *args, prioridad=0, **kwargs):
        llamadas.append((tipo, ref_id))
        llamadas.params.append(kwargs)
        llamadas.prioridades.append(prioridad)
        return len(llamadas)

    monkeypatch.setattr(queue, "encolar", falso)
    return llamadas


@pytest.fixture
def client(engine, jobs_encolados):
    """Cliente de la API. Sin `with`: no corre el lifespan (ni worker ni llama-server)."""
    from backend.main import app

    return TestClient(app)


# --- Clients falsos ---------------------------------------------------------
# Las etapas usan `comfy.generar_imagen(...)`, o sea, buscan el atributo en el
# módulo en cada llamada: parchear el módulo basta, no hace falta tocar las
# etapas. Se importan los módulos reales solo para sustituirles las funciones.

def _instalar(monkeypatch, nombre_modulo: str, fake):
    import importlib

    modulo = importlib.import_module(f"backend.clients.{nombre_modulo}")
    for nombre in fake.PUBLICOS:
        monkeypatch.setattr(modulo, nombre, getattr(fake, nombre))
    return fake


@pytest.fixture
def fake_llm(monkeypatch):
    from tests.fakes import FakeLLM

    return _instalar(monkeypatch, "llm", FakeLLM())


@pytest.fixture
def fake_comfy(monkeypatch):
    from tests.fakes import FakeComfy

    return _instalar(monkeypatch, "comfy", FakeComfy())


@pytest.fixture
def fake_stt(monkeypatch):
    from tests.fakes import FakeSTT

    return _instalar(monkeypatch, "stt", FakeSTT())


@pytest.fixture
def fake_rife(monkeypatch):
    from tests.fakes import FakeRife

    return _instalar(monkeypatch, "rife", FakeRife())


@pytest.fixture
def fake_fondo(monkeypatch):
    from tests.fakes import FakeFondo

    return _instalar(monkeypatch, "fondo", FakeFondo())


@pytest.fixture
def fake_tts(monkeypatch):
    from tests.fakes import FakeTTS

    return _instalar(monkeypatch, "tts", FakeTTS())


@pytest.fixture
def parada_pedida():
    """Deja la bandera de parada encendida, como si el usuario ya hubiera
    pulsado el botón mientras este job corría."""
    from backend import parada

    parada.iniciar(1)
    parada.marcar(1)
    yield
    parada.limpiar()


@pytest.fixture(autouse=True)
def pid_del_llm_aislado(monkeypatch, tmp_path):
    """Aparta el `logs/llm.pid` real de la máquina. **Autouse a propósito.**

    Ese fichero no es un dato cualquiera: guarda el pgid del llama-server vivo
    para que, al arrancar, el backend adopte o remate al huérfano de la
    ejecución anterior (`_matar_pgid`). Con la ruta real puesta, un test que
    pase por ahí borra el pid de una sesión en marcha —o mata su grupo de
    procesos—, y además deja la suite dependiendo de si el fichero existía:
    el 2026-10-20 un test de memoria fallaba o pasaba según eso, y es el mejor
    candidato a los dos fallos intermitentes que no se reprodujeron el día
    anterior. `dirs_tmp` redirige las carpetas de salida, pero esta no.
    """
    from backend.services import llm_runtime

    monkeypatch.setattr(llm_runtime, "ARCHIVO_PID", tmp_path / "llm.pid")


@pytest.fixture
def dirs_tmp(monkeypatch, tmp_path):
    """Redirige las carpetas de salida (proyectos/, voces/, reparto/, galeria/, musica/) a un tmp.

    Los módulos hacen `from ...config import PROYECTOS_DIR`, así que no basta
    con parchear config: se parchea el nombre en cada módulo de `backend` que
    lo importó (hay que importarlos todos antes para que existan).
    """
    import importlib
    import pkgutil
    import sys

    import backend

    for m in pkgutil.walk_packages(backend.__path__, "backend."):
        importlib.import_module(m.name)

    dirs = {}
    for nombre, carpeta in (("PROYECTOS_DIR", "proyectos"), ("VOCES_DIR", "voces"),
                            ("REPARTO_DIR", "reparto"), ("GALERIA_DIR", "galeria"),
                            ("MUSICA_DIR", "musica")):
        destino = tmp_path / carpeta
        destino.mkdir()
        dirs[carpeta] = destino
        for mod_nombre, mod in list(sys.modules.items()):
            if mod_nombre.startswith("backend") and hasattr(mod, nombre):
                monkeypatch.setattr(mod, nombre, destino)
    return dirs


@pytest.fixture
def http_mock(monkeypatch):
    """Sustituye `httpx.Client` por uno con transporte simulado.

    Los clients crean su `httpx.Client` dentro de cada llamada, así que se
    parchea la clase: `http_mock(handler)` y todo cliente nuevo habla con
    `handler(request) -> httpx.Response` en vez de con la red. Devuelve la lista
    de peticiones vistas.
    """
    real = httpx.Client

    def instalar(handler):
        vistas: list[httpx.Request] = []

        def registrando(request):
            vistas.append(request)
            return handler(request)

        def fabrica(*args, **kwargs):
            kwargs.pop("transport", None)
            return real(*args, transport=httpx.MockTransport(registrando), **kwargs)

        monkeypatch.setattr(httpx, "Client", fabrica)
        return vistas

    return instalar


@pytest.fixture(autouse=True)
def ningun_llama_server_de_verdad(monkeypatch):
    """Hace cierta la primera línea de este fichero por el lado del LLM.

    Hizo falta el 2026-10-23. Mientras `llm_runtime` «adoptaba y no tocaba» el
    servidor que encontrase puesto, la suite era inofensiva por accidente: no
    había camino que matara un proceso. Al pasar a hacerse cargo de él
    (`_tomar_el_mando`, que es lo que arregla los 18 GiB de swap de la voz) ese
    camino existe, y una tanda de tests mató el llama-server que había en el
    9876 y lanzó otro de 17 GiB llamando a `~/Models/*.sh` de verdad.

    Se tapa el borde entero —procesos y red—, no un caso. Un test que quiera
    probar esos caminos pone sus propios dobles y gana, porque su monkeypatch
    se aplica después de este.
    """
    from backend.clients import comfy, llm
    from backend.services import llm_runtime
    from backend.workers import queue

    # Se sustituye el nombre con el que `llm_runtime` ve al cliente, y no las
    # funciones del cliente: así los tests del propio cliente siguen probando
    # las de verdad.
    monkeypatch.setattr(llm_runtime, "llm", _ClienteSinServidor(llm))
    # Igual con ComfyUI: los dos sitios que esperan memoria antes de cargar un
    # modelo le mandan un /free, y en los tests eso iba al ComfyUI de verdad —
    # y además ataba el resultado a cuánta memoria tuviera la máquina.
    monkeypatch.setattr(llm_runtime, "comfy", _ComfySinModelos(comfy))
    monkeypatch.setattr(queue, "comfy", _ComfySinModelos(comfy))
    monkeypatch.setattr(llm_runtime, "_pids_en_puerto", lambda url: [])
    monkeypatch.setattr(llm_runtime, "_lanzar", lambda modelo: _ProcDeTest())
    monkeypatch.setattr(llm_runtime, "_matar", lambda proc: None)
    monkeypatch.setattr(llm_runtime, "_matar_pgid", lambda pgid: None)
    monkeypatch.setattr(llm_runtime, "_rematar_el_puerto", lambda url: None)
    monkeypatch.setattr(llm_runtime, "_anotar_pid", lambda modelo, proc: None)
    monkeypatch.setattr(llm_runtime, "_olvidar_pid", lambda: None)
    # El estado del módulo es global y la cola corre de verdad en varios tests:
    # sin esto, un test que deja un modelo «cargado» se lo pasa al siguiente.
    monkeypatch.setattr(llm_runtime, "_proc", None)
    monkeypatch.setattr(llm_runtime, "_proc_modelo", "")
    monkeypatch.setattr(llm_runtime, "_tomado", None)
    monkeypatch.setattr(llm_runtime, "_tomado_gb", 0.0)


class _ClienteSinServidor:
    """El cliente del LLM visto por `llm_runtime`: nadie escucha en ningún
    puerto. Lo demás lo pasa al cliente de verdad."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)

    def ping(self, url=None):
        return False

    def que_hay(self, url=None):
        return None


class _ComfySinModelos:
    """ComfyUI visto por quien va a cargar un modelo: no responde, así que no
    retiene nada ni se le manda un /free de verdad. Lo demás lo pasa al
    cliente real."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)

    def liberar_memoria(self, hasta_gb=None):
        return self._real.Liberacion(None, None, 0.0, 0, True)


class _ProcDeTest:
    """Un llama-server que no existe pero está «vivo»."""

    def poll(self):
        return None
