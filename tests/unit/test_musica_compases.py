from backend.services import musica_compases as c

GUION = """[Intro - 4 bars - piano alone]
[Theme A (16 bars) - sax states the theme]
[Break, 8 bars, drums out]
[Solo - 48 bars - sax improvises over the groove]
[Outro - 8 bars - last phrase, final chord rings out]"""


def test_lee_los_compases_de_cada_formato():
    assert [n for _, n in c.secciones(GUION)] == [4, 16, 8, 48, 8]
    assert c.secciones(GUION)[1][0] == "Theme A - sax states the theme"


def test_quita_los_compases_sin_tocar_el_resto():
    assert c.quitar_compases(GUION).splitlines() == [
        "[Intro - piano alone]",
        "[Theme A - sax states the theme]",
        "[Break, drums out]",
        "[Solo - sax improvises over the groove]",
        "[Outro - last phrase, final chord rings out]",
    ]
    assert c.quitar_compases("[Intro]\n[Verse 1 - whispered]") == "[Intro]\n[Verse 1 - whispered]"


def test_la_duracion_sale_de_los_compases_y_el_tempo():
    # 84 compases × 4 tiempos × 60 / 120 bpm = 168 s, más la cola.
    assert c.duracion_desde_guion(GUION, 120, "4") == 168 + c.COLA_S
    # Mismo guion más lento: más largo, mismos compases.
    assert c.duracion_desde_guion(GUION, 84, "4") == 240 + c.COLA_S
    assert c.duracion_desde_guion(GUION, 120, "3") == 126 + c.COLA_S
    assert c.duracion_desde_guion("[Intro]\n[Outro]", 120, "4") is None


def test_un_guion_bien_hecho_pasa():
    assert c.problemas(GUION) == []


def test_rechaza_las_vueltas_eternas_y_los_finales_sin_componer():
    malo = "[Intro - 4 bars - x]\n[Vamp - 40 bars - groove]\n[Vamp - 40 bars - groove]\n[Theme - x]"
    p = " | ".join(c.problemas(malo))
    assert "sin compases" in p
    assert "vuelta estirada" in p
    assert "se repite seguida" in p
    assert "no es un final" in p


def test_un_guion_de_dos_secciones_no_vale():
    assert c.problemas("[Intro - 4 bars]\n[Outro - 4 bars]")


def test_con_el_tempo_una_seccion_larga_es_un_bloque():
    # A 75 bpm un compás de 4 son 3,2 s: 12 compases son 38 s, un bloque.
    lento = (
        "[Intro - 5 bars - bass alone]\n[Theme - 12 bars - bass states the theme]\n"
        "[Climb - 7 bars - higher]\n[Outro - 6 bars - fades]"
    )
    p = c.problemas(lento, 75, "4")
    assert len(p) == 1 and "«Theme" in p[0] and "38 s" in p[0]
    # El mismo guion a 140 bpm cabe: 12 compases son 21 s.
    assert c.problemas(lento, 140, "4") == []
    # Sin tempo no se mide en segundos.
    assert c.problemas(lento) == []


def test_un_solo_tiene_algo_mas_de_margen():
    g = "[Intro - 4 bars - x]\n[Solo - 16 bars - sax]\n[Theme - 6 bars - y]\n[Outro - 5 bars - z]"
    # 16 compases a 120 bpm son 32 s: vale para un solo, no para otra sección.
    assert c.problemas(g, 120, "4") == []
    assert "máximo es 25 s" in " ".join(c.problemas(g.replace("Solo", "Vamp"), 120, "4"))


def test_tres_secciones_seguidas_iguales_son_forma_cuadrada():
    cuadrado = "[Intro - 8 bars - a]\n[A - 8 bars - b]\n[B - 8 bars - c]\n[Outro - 6 bars - d]"
    assert "forma cuadrada" in " ".join(c.problemas(cuadrado))
    assert c.problemas(cuadrado.replace("[A - 8", "[A - 7")) == []
