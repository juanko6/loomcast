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
        assert c.execute(text("SELECT slug FROM proyectos")).scalar() == "viejo"


def test_migrar_es_idempotente(engine):
    db_mod._migrar()
    db_mod._migrar()
