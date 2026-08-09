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

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(escenas)"))]
        nuevas = {
            "prompt_movimiento": "TEXT DEFAULT ''",
            "modo": "VARCHAR DEFAULT ''",
            "clip_modo": "VARCHAR DEFAULT ''",
            "imagen_s": "FLOAT DEFAULT 0",
            "clip_s": "FLOAT DEFAULT 0",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE escenas ADD COLUMN {col} {tipo}"))
        c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(imagenes_libres)"))]
        if "motor" not in cols:
            c.execute(
                text("ALTER TABLE imagenes_libres ADD COLUMN motor VARCHAR DEFAULT ''")
            )
            c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(jobs)"))]
        if "params" not in cols:
            c.execute(text("ALTER TABLE jobs ADD COLUMN params TEXT DEFAULT '{}'"))
            c.commit()

        # Conditioning musical de ACE-Step 1.5 (las pistas de v1 se quedan con
        # estos valores por defecto; da igual, hay que regenerarlas de todos
        # modos porque el modelo cambió).
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(musicas)"))]
        nuevas = {
            "bpm": "INTEGER DEFAULT 120",
            "keyscale": "VARCHAR DEFAULT 'C major'",
            "timesig": "VARCHAR DEFAULT '4'",
            "idioma": "VARCHAR DEFAULT 'es'",
            "portada": "TEXT",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE musicas ADD COLUMN {col} {tipo}"))
        c.commit()


def get_session() -> Session:
    return SessionLocal()
