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
        # Y de qué serie es episodio. Un proyecto de antes de las series se
        # queda sin serie y con el episodio en 0, que es la verdad: es un vídeo
        # suelto y el pipeline lo trata como siempre.
        assert {"serie_id", "episodio", "resumen_episodio"} <= set(cols)
        fila = c.execute(text(
            "SELECT slug, serie_id, episodio, resumen_episodio FROM proyectos"
        )).one()
        assert fila == ("viejo", None, 0, "")


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


def test_migrar_recoloca_el_reparto_que_quedo_marcado_persona(engine):
    """Las filas anteriores al tipo se quedaron con el default "persona", y
    entre ellas había objetos: con ese tipo su referencia se seguiría generando
    con encuadre de retrato, o sea con una cara pintada encima."""
    with engine.begin() as c:
        c.execute(text("DELETE FROM personajes"))
        for i, (clave, ficha) in enumerate([
            ("COFRE", "an 18th-century wooden treasure chest, constructed from dark "
                      "weathered oak planks with rusted iron hinges"),
            ("ANA", "a woman in her forties with pale skin, dark hair and green eyes, "
                    "wearing a grey coat"),
        ]):
            c.execute(text(
                "INSERT INTO personajes (id, proyecto_id, orden, clave, nombre, ficha, "
                "seed, tipo, reparto_slug, voz, created_at) VALUES (:id, 1, :orden, "
                ":clave, '', :ficha, 1, 'persona', '', '', '2026-01-01')"
            ), {"id": i + 1, "orden": i, "clave": clave, "ficha": ficha})

    db_mod._migrar()

    with engine.connect() as c:
        tipos = dict(c.execute(text("SELECT clave, tipo FROM personajes")).all())
    assert tipos == {"COFRE": "objeto", "ANA": "persona"}


def test_migrar_no_toca_un_objeto_ya_decidido(engine):
    """Un "objeto" lo puso el casting: la migración no lo revisa."""
    with engine.begin() as c:
        c.execute(text("DELETE FROM personajes"))
        c.execute(text(
            "INSERT INTO personajes (id, proyecto_id, orden, clave, nombre, ficha, "
            "seed, tipo, reparto_slug, voz, created_at) VALUES (1, 1, 0, 'RARO', '', "
            "'a woman in her forties with dark hair and green eyes, wearing a coat', "
            "1, 'objeto', '', '', '2026-01-01')"
        ))

    db_mod._migrar()

    with engine.connect() as c:
        assert c.execute(text("SELECT tipo FROM personajes")).scalar() == "objeto"
