from sqlalchemy import text

from backend import db as db_mod


def test_migrar_anade_columnas_a_una_bd_antigua(engine):
    """Una BD previa al selector de voz/i2v/música no pierde datos al migrar."""
    with engine.begin() as c:
        c.execute(text("DROP TABLE proyectos"))
        c.execute(text("CREATE TABLE proyectos (id INTEGER PRIMARY KEY, slug VARCHAR)"))
        c.execute(text("INSERT INTO proyectos (slug) VALUES ('viejo')"))

    db_mod._migrar()

    with engine.connect() as c:
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(proyectos)"))]
        assert "voz" in cols
        # La música del proyecto: su pista y si el armado la mezcla.
        assert "musica_id" in cols and "musica_mezclar" in cols
        assert c.execute(text("SELECT slug FROM proyectos")).scalar() == "viejo"


def test_migrar_anade_los_intentos_a_los_jobs_viejos(engine):
    """Los jobs de antes de los reintentos se quedan en 0, que es lo que se sabe."""
    with engine.begin() as c:
        c.execute(text("DROP TABLE jobs"))
        c.execute(text(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY, tipo VARCHAR, ref_id INTEGER, "
            "estado VARCHAR, log TEXT, created_at DATETIME)"
        ))
        c.execute(text("INSERT INTO jobs (tipo, ref_id, estado) VALUES ('generar_voz', 1, 'ok')"))

    db_mod._migrar()

    with engine.connect() as c:
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(jobs)"))]
        assert "intentos" in cols and "params" in cols
        assert c.execute(text("SELECT intentos FROM jobs")).scalar() == 0


def test_migrar_es_idempotente(engine):
    db_mod._migrar()
    db_mod._migrar()
