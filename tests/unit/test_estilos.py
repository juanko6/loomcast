import pytest

from backend import estilos


def _estilo(raiz, eid, toml):
    d = raiz / eid
    d.mkdir(parents=True)
    (d / "estilo.toml").write_text(toml)
    return d


@pytest.fixture
def raiz(monkeypatch, tmp_path):
    monkeypatch.setattr(estilos, "ESTILOS_DIR", tmp_path)
    return tmp_path


def test_listar_ordena_por_orden_y_cuenta_solo_ejemplos_de_imagen(raiz):
    b = _estilo(raiz, "b", 'nombre = "B"\ncabecera = "bb"\norden = 1\n')
    _estilo(raiz, "a", 'nombre = "A"\ncabecera = "aa"\norden = 2\n')
    (raiz / "suelto").mkdir()  # sin estilo.toml: no es un estilo
    for n in ("ejemplo_2.webp", "ejemplo_1.png", "ejemplo_3.txt", "otra.png"):
        (b / n).write_bytes(b"x")
    lista = estilos.listar()
    assert [e.id for e in lista] == ["b", "a"]
    assert [p.name for p in lista[0].ejemplos] == ["ejemplo_1.png", "ejemplo_2.webp"]


def test_sin_carpeta_no_hay_estilos(monkeypatch, tmp_path):
    monkeypatch.setattr(estilos, "ESTILOS_DIR", tmp_path / "no")
    assert estilos.listar() == []


@pytest.mark.parametrize("toml, error", [
    ('cabecera = "x"\n', "nombre"),
    ('nombre = "X"\ncabecera = "  "\n', "cabecera"),
    ('nombre = "X"\ncabecera = "x"\nmotor = "qwen"\n', "no sabe generar"),
    ('nombre = "X"\ncabecera = "x"\nmotor = "inventado"\n', "no existe"),
])
def test_un_estilo_mal_escrito_dice_que_le_falta(raiz, toml, error):
    _estilo(raiz, "malo", toml)
    with pytest.raises(ValueError, match=error):
        estilos.obtener("malo")


@pytest.mark.parametrize("eid", ["", "nada", "../x", ".oculto", "a/b"])
def test_obtener_rechaza_ids_que_no_son_un_estilo(raiz, eid):
    with pytest.raises(estilos.EstiloNoExiste):
        estilos.obtener(eid)


def test_componer_pone_el_estilo_delante_y_detras_y_junta_los_espacios(raiz):
    _estilo(raiz, "t", 'nombre = "T"\ncabecera = """flat   ink,\n two colors."""\ncola = "grain"\n')
    e = estilos.obtener("t")
    assert estilos.componer(e, " a cat on a stool. ") == "flat ink, two colors. a cat on a stool. grain."


def test_componer_sin_cola(raiz):
    _estilo(raiz, "t", 'nombre = "T"\ncabecera = "flat"\n')
    assert estilos.componer(estilos.obtener("t"), "a cat") == "flat. a cat."
