"""Fixtures comunes. Ningún test toca loomcast.db, ComfyUI, el LLM ni la GPU."""
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

    llamadas: list[tuple] = []

    def falso(tipo, ref_id, *args, **kwargs):
        llamadas.append((tipo, ref_id))
        return len(llamadas)

    monkeypatch.setattr(queue, "encolar", falso)
    return llamadas


@pytest.fixture
def client(engine, jobs_encolados):
    """Cliente de la API. Sin `with`: no corre el lifespan (ni worker ni llama-server)."""
    from backend.main import app

    return TestClient(app)
