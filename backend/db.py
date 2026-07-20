"""Engine y sesiones SQLite (acceso desde API y worker en hilos distintos)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DB_PATH
from .models import Base

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrar()


def _migrar() -> None:
    """Migraciones mínimas: create_all no altera tablas existentes."""
    from sqlalchemy import text

    with engine.connect() as c:
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(proyectos)"))]
        if "voz" not in cols:
            c.execute(text("ALTER TABLE proyectos ADD COLUMN voz VARCHAR"))
            c.commit()


def get_session() -> Session:
    return SessionLocal()
