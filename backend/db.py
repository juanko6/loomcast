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

        # La pista de música del proyecto y si se mezcla en el video final.
        nuevas = {
            "musica_id": "INTEGER",
            "musica_mezclar": "BOOLEAN DEFAULT 0",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE proyectos ADD COLUMN {col} {tipo}"))
        c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(escenas)"))]
        nuevas = {
            "prompt_movimiento": "TEXT DEFAULT ''",
            "modo": "VARCHAR DEFAULT ''",
            "clip_modo": "VARCHAR DEFAULT ''",
            "imagen_s": "FLOAT DEFAULT 0",
            "clip_s": "FLOAT DEFAULT 0",
            "personajes": "VARCHAR DEFAULT ''",
            "clip_motor": "VARCHAR DEFAULT ''",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE escenas ADD COLUMN {col} {tipo}"))
        c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(personajes)"))]
        # De qué miembro del reparto propio se trajo (vacío = nació en este
        # proyecto). Los repartos de antes del reparto persistente se quedan en
        # "", que es la verdad: ninguno venía de ningún sitio.
        if "reparto_slug" not in cols:
            c.execute(
                text("ALTER TABLE personajes ADD COLUMN reparto_slug VARCHAR DEFAULT ''")
            )
            c.commit()
        if "tipo" not in cols:
            c.execute(
                text("ALTER TABLE personajes ADD COLUMN tipo VARCHAR DEFAULT 'persona'")
            )
            c.commit()
        # El reparto que ya existía se quedó con el default "persona", y ahí
        # había objetos: un cofre, un Motorola DynaTAC, un robot, un mapa. Con
        # ese tipo su referencia se seguiría generando con encuadre de retrato,
        # o sea con una cara pintada encima, así que se reclasifican por su
        # ficha. Solo las "persona": una "objeto" ya la decidió el casting.
        # El import va aquí dentro porque el clasificador vive en el pipeline y
        # a nivel de módulo sería un ciclo.
        from .services.pipeline.casting import normalizar_tipo

        recolocadas = [
            fila[0]
            for fila in c.execute(text(
                "SELECT id, ficha FROM personajes WHERE tipo = 'persona'"
            ))
            if normalizar_tipo("persona", fila[1] or "") == "objeto"
        ]
        for pid in recolocadas:
            c.execute(
                text("UPDATE personajes SET tipo = 'objeto' WHERE id = :id"),
                {"id": pid},
            )
        if recolocadas:
            c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(imagenes_libres)"))]
        if "motor" not in cols:
            c.execute(
                text("ALTER TABLE imagenes_libres ADD COLUMN motor VARCHAR DEFAULT ''")
            )
            c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(jobs)"))]
        nuevas = {
            "params": "TEXT DEFAULT '{}'",
            # Intentos del job: los de antes de los reintentos quedan en 0, que
            # es lo que de verdad se sabe de ellos.
            "intentos": "INTEGER DEFAULT 0",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {tipo}"))
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
