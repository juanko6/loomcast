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

        # La pista de música del proyecto y si se mezcla en el video final, y
        # de qué serie es episodio. Los proyectos de antes de las series se
        # quedan con serie_id NULL y episodio 0, que es la verdad: son vídeos
        # sueltos y el pipeline los trata como siempre.
        nuevas = {
            "musica_id": "INTEGER",
            "musica_mezclar": "BOOLEAN DEFAULT 0",
            "serie_id": "INTEGER",
            "episodio": "INTEGER DEFAULT 0",
            "resumen_episodio": "TEXT DEFAULT ''",
            # De qué versión del guion salió el resumen, qué se salió del tramo
            # del hilo y si un episodio anterior se reescribió por detrás. Los
            # episodios de antes del hilo quedan en 0 / "" / 0, que es la
            # verdad: su resumen se escribió al armar el vídeo, cuando no había
            # ni tramos que cumplir ni versiones que comparar.
            "resumen_version": "INTEGER DEFAULT 0",
            "tramo_desvio": "TEXT DEFAULT ''",
            "continuidad_rota": "BOOLEAN DEFAULT 0",
            # Cuándo se subió a YouTube, dónde quedó y la nota de quien lo
            # subió. Los proyectos de antes de la publicación quedan en "",
            # o sea sin publicar: es lo único que esta máquina sabe de ellos.
            "publicado_en": "VARCHAR DEFAULT ''",
            "publicado_url": "VARCHAR DEFAULT ''",
            "publicado_nota": "TEXT DEFAULT ''",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE proyectos ADD COLUMN {col} {tipo}"))
        c.commit()

        # Los episodios que ya tenían resumen lo escribieron al armar el vídeo,
        # cuando no había versiones que comparar. Se les apunta la versión del
        # guion que tenían entonces (la última), que es lo más cerca de la
        # verdad a la que se puede llegar ahora. Sin esto saldrían todos como
        # "el canon es de otra versión" y el autopiloto los reescribiría encima,
        # incluidos los que se corrigieron a mano.
        c.execute(text(
            "UPDATE proyectos SET resumen_version = COALESCE((SELECT MAX(version) "
            "FROM guiones WHERE guiones.proyecto_id = proyectos.id), 0) "
            "WHERE resumen_version = 0 "
            "AND TRIM(COALESCE(resumen_episodio, '')) != ''"
        ))
        c.commit()

        # La premisa de la que sale el hilo y cuántos episodios se pidieron.
        # Las series de antes del hilo se quedan con "" y 0: siguen produciendo
        # episodios con la continuidad hacia atrás de siempre, y escribirles un
        # hilo es pedirlo desde su pantalla.
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(series)"))]
        nuevas = {
            "premisa": "TEXT DEFAULT ''",
            "episodios_objetivo": "INTEGER DEFAULT 0",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE series ADD COLUMN {col} {tipo}"))
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
        # Con qué voz del banco dice sus líneas. Los repartos de antes de la voz
        # por personaje se quedan en "", que es la verdad: lo narraba todo la
        # voz del proyecto.
        if "voz" not in cols:
            c.execute(text("ALTER TABLE personajes ADD COLUMN voz VARCHAR DEFAULT ''"))
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

        # La voz del miembro del reparto propio, que viaja con él a cada vídeo
        # nuevo igual que su ficha y su cara.
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(reparto)"))]
        if "voz" not in cols:
            c.execute(text("ALTER TABLE reparto ADD COLUMN voz VARCHAR DEFAULT ''"))
            c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(imagenes_libres)"))]
        if "motor" not in cols:
            c.execute(
                text("ALTER TABLE imagenes_libres ADD COLUMN motor VARCHAR DEFAULT ''")
            )
            c.commit()
        # El tipo `animada`. Las entradas de antes no tienen vídeo, así que se
        # quedan con el prompt de movimiento vacío, la duración por defecto y
        # sin semilla ni escala, que es la verdad.
        nuevas = {
            "prompt_movimiento": "TEXT DEFAULT ''",
            "duracion_s": "INTEGER DEFAULT 12",
            "seed_video": "INTEGER",
            "escala": "VARCHAR",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE imagenes_libres ADD COLUMN {col} {tipo}"))
        c.commit()

        cols = [r[1] for r in c.execute(text("PRAGMA table_info(jobs)"))]
        nuevas = {
            "params": "TEXT DEFAULT '{}'",
            # Intentos del job: los de antes de los reintentos quedan en 0, que
            # es lo que de verdad se sabe de ellos.
            "intentos": "INTEGER DEFAULT 0",
            # Orden en la cola. Los jobs de antes de la prioridad quedan en 0,
            # o sea "pedido a mano", que es lo que eran todos: el autopiloto no
            # existía.
            "prioridad": "INTEGER DEFAULT 0",
        }
        for col, tipo in nuevas.items():
            if col not in cols:
                c.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {tipo}"))
        c.commit()

        # Con qué narra cada tirada. Las de antes de la narración expresiva
        # quedan en "clon", que es lo único que sabían hacer: clonar la voz del
        # banco que se les eligió al lanzarlas.
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(autopilotos)"))]
        if "narracion" not in cols:
            c.execute(
                text("ALTER TABLE autopilotos ADD COLUMN narracion "
                     "VARCHAR DEFAULT 'clon'")
            )
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
