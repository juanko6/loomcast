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
        # comparaciones de los tests que solo miran (tipo, ref_id).
        params: list[dict]

    llamadas = Llamadas()
    llamadas.params = []

    def falso(tipo, ref_id, *args, **kwargs):
        llamadas.append((tipo, ref_id))
        llamadas.params.append(kwargs)
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
def dirs_tmp(monkeypatch, tmp_path):
    """Redirige las carpetas de salida (proyectos/, voces/, galeria/, musica/) a un tmp.

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
                            ("GALERIA_DIR", "galeria"), ("MUSICA_DIR", "musica")):
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
