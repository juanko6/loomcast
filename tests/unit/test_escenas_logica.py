import pytest

from backend.services.pipeline import escenas


def _palabras(*tiempos):
    return [{"word": f" p{i}", "start": s, "end": e} for i, (s, e) in enumerate(tiempos)]


# --- _segmentar -------------------------------------------------------------

def test_segmentar_reparte_en_intervalos_parecidos():
    ws = _palabras(*[(i * 1.0, i * 1.0 + 0.5) for i in range(8)])  # 0..7.5 s
    segs = escenas._segmentar(ws, 4)
    assert len(segs) == 2
    assert [s["texto"].split() for s in segs] == [["p0", "p1", "p2", "p3"], ["p4", "p5", "p6", "p7"]]
    assert segs[-1]["t_fin"] == 7.5  # el último llega al final real del audio


def test_segmentar_una_sola_palabra():
    segs = escenas._segmentar(_palabras((0, 0.4)), 4)
    assert segs == [{"t_inicio": 0.0, "t_fin": 0.4, "texto": "p0"}]


def test_segmentar_descarta_intervalos_sin_palabras():
    # Un silencio largo en medio deja un intervalo vacío: no genera escena.
    ws = _palabras((0, 0.5), (0.6, 1.0), (11.0, 11.5))
    segs = escenas._segmentar(ws, 4)
    assert [s["texto"] for s in segs] == ["p0 p1", "p2"]


def test_segmentar_sin_palabras_falla():
    with pytest.raises(IndexError):
        escenas._segmentar([], 4)


# --- casting ----------------------------------------------------------------

FICHAS = {"ANA": "a woman in her thirties with dark curls, wearing a red coat"}


@pytest.mark.parametrize("ficha,esperado", [
    ("a woman in her thirties with dark curls", "a woman in her thirties"),
    ("a man, tall, bearded", "a man"),
    ("a girl wearing a hat", "a girl"),
    ("one two three four five six seven eight nine ten", "one two three four five six seven eight"),
    ("", ""),
])
def test_breve(ficha, esperado):
    assert escenas._breve(ficha) == esperado


def test_aplicar_casting_sustituye_el_marcador_por_la_ficha():
    prompt, quienes = escenas._aplicar_casting("{ANA} walks in the rain", FICHAS)
    assert prompt == f"{FICHAS['ANA']} walks in the rain" and quienes == ["ANA"]


def test_aplicar_casting_en_modo_breve():
    prompt, _ = escenas._aplicar_casting("{ANA} runs", FICHAS, breve=True)
    assert prompt == "a woman in her thirties runs"


def test_aplicar_casting_clave_pelada():
    """El modelo a veces escribe MADRASTRA sin llaves: igualmente cuenta."""
    prompt, quienes = escenas._aplicar_casting("ANA stands alone", FICHAS)
    assert prompt.startswith(FICHAS["ANA"]) and quienes == ["ANA"]


def test_aplicar_casting_no_confunde_palabras_en_minuscula_ni_subcadenas():
    prompt, quienes = escenas._aplicar_casting("banana ana ANALOG", FICHAS)
    assert prompt == "banana ana ANALOG" and quienes == []


def test_aplicar_casting_marcador_huerfano_pierde_las_llaves():
    prompt, quienes = escenas._aplicar_casting("{INVENTADO} appears", FICHAS)
    assert prompt == "INVENTADO appears" and quienes == []


def test_aplicar_casting_sin_fichas_deja_el_prompt():
    assert escenas._aplicar_casting("un prompt", {}) == ("un prompt", [])


def test_aplicar_casting_no_duplica_si_sale_dos_veces():
    _, quienes = escenas._aplicar_casting("{ANA} y ANA", FICHAS)
    assert quienes == ["ANA"]


def test_detectar_personajes_en_prompt_completo_y_abreviado():
    assert escenas.detectar_personajes(f"{FICHAS['ANA']} sits", FICHAS) == ["ANA"]
    assert escenas.detectar_personajes("a woman in her thirties runs", FICHAS) == ["ANA"]
    assert escenas.detectar_personajes("a dog barks", FICHAS) == []
    assert escenas.detectar_personajes("x", {"ANA": ""}) == []


def test_bloque_casting_vacio_si_no_hay_reparto():
    assert escenas._bloque_casting({}) == ""
    bloque = escenas._bloque_casting(FICHAS)
    assert "- {ANA}: a woman" in bloque and "do not invent markers" in bloque
