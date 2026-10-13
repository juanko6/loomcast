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


# --- _quitar_eco ------------------------------------------------------------

ROBOT = ("a vintage 1970s industrial robot with a boxy metallic chassis, "
         "exposed wiring, and wheeled treads")


@pytest.mark.parametrize("prompt, queda", [
    # Aposición detrás, aunque traiga varias comas
    ("Close-up of {R}, a vintage 1970s industrial robot with a boxy chassis, "
     "exposed wiring, standing in a lab", "Close-up of {R}, standing in a lab"),
    # Descripción delante del marcador
    ("A vintage industrial robot {R} frozen mid-motion", "{R} frozen mid-motion"),
    ("Close-up of a robot {R} near the door", "Close-up of {R} near the door"),
    # Lo que no repite la ficha se queda
    ("A close-up of {R} in a lab", "A close-up of {R} in a lab"),
    ("{R}, a lone survivor of the fire, rolls on", "{R}, a lone survivor of the fire, rolls on"),
    ("{R}’s sensor head turns slowly", "{R}’s sensor head turns slowly"),
])
def test_quitar_eco_quita_solo_lo_que_repite_la_ficha(prompt, queda):
    assert escenas._quitar_eco(prompt, "{R}", ROBOT) == queda


def test_aplicar_casting_no_duplica_la_ficha_que_el_llm_repite():
    prompt, _ = escenas._aplicar_casting(
        "{R}, a vintage industrial robot with a boxy metallic chassis, rolls forward",
        {"R": ROBOT})
    assert prompt == f"{ROBOT}, rolls forward"


def test_aplicar_casting_articulo_suelto_delante_del_marcador_sobra():
    prompt, _ = escenas._aplicar_casting("Close-up of the {R} on a bench", {"R": ROBOT})
    assert prompt == f"Close-up of {ROBOT} on a bench"


def test_aplicar_casting_marcador_repetido_lleva_la_ficha_una_vez():
    prompt, quienes = escenas._aplicar_casting(
        "A man pushes {R}. {R} resists, and R stays put", {"R": ROBOT})
    assert prompt.count("boxy metallic chassis") == 1
    assert prompt.endswith("the vintage 1970s industrial robot resists, and "
                           "the vintage 1970s industrial robot stays put")
    assert quienes == ["R"]


def test_breve_no_deja_la_frase_colgando():
    assert escenas._breve("a compact silver digital camera from the late 1980s, "
                          "black lens") == "a compact silver digital camera"


def test_aplicar_casting_aposicion_con_coma_delante():
    prompt, _ = escenas._aplicar_casting("Close-up of a vintage robot, {R}, on a bench", {"R": ROBOT})
    assert prompt == f"Close-up of {ROBOT}, on a bench"


def test_aplicar_casting_reconoce_al_personaje_descrito_sin_marcador():
    _, quienes = escenas._aplicar_casting("a vintage 1970s industrial robot rolls on", {"R": ROBOT})
    assert quienes == ["R"]
