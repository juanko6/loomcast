"""El corte de la narración en frases y su reparto en escenas.

Lo que se prueba aquí es la condición que no se puede romper: la voz ya está
grabada, así que la suma de las escenas tiene que seguir siendo el audio, caiga
donde caiga el corte. Que una escena dure dos segundos y la siguiente nueve es
el objetivo; que una dure cero, o que se quede una frase sin escena, es un
vídeo roto.
"""
from backend.services.pipeline import _motion_frases as mf


def palabras(texto: str, paso: float = 0.4) -> list[dict]:
    """Un `palabras.json` de mentira: cada palabra dura lo mismo."""
    return [{"word": f" {w}", "start": round(i * paso, 3),
             "end": round((i + 1) * paso, 3)}
            for i, w in enumerate(texto.split())]


# --- frases -----------------------------------------------------------------

def test_cada_punto_abre_frase():
    fs = mf.frases(palabras("Uno dos tres. Cuatro cinco seis."))
    assert [f["texto"] for f in fs] == ["Uno dos tres.", "Cuatro cinco seis."]


def test_un_punto_seguido_de_minuscula_no_corta():
    """«etc. y entonces» es una frase, no dos: el punto de una abreviatura no
    termina nada. Por eso se mira también lo que viene detrás."""
    fs = mf.frases(palabras("Vale etc. y entonces pasa esto."))
    assert len(fs) == 1


def test_los_tiempos_son_los_del_audio():
    fs = mf.frases(palabras("Uno dos. Tres cuatro.", paso=0.5))
    assert (fs[0]["t_inicio"], fs[0]["t_fin"]) == (0.0, 1.0)
    assert (fs[1]["t_inicio"], fs[1]["t_fin"]) == (1.0, 2.0)


def test_lo_ultimo_sin_punto_tambien_es_una_frase():
    fs = mf.frases(palabras("Uno dos. Y esto se queda sin punto"))
    assert len(fs) == 2 and fs[-1]["texto"].endswith("punto")


def test_una_frase_kilometrica_se_parte_por_la_coma():
    larga = " ".join(["palabra"] * 14) + ", " + " ".join(["otra"] * 14) + "."
    fs = mf.frases(palabras(larga))
    assert len(fs) == 2
    # Y el corte no inventa tiempo: la segunda empieza donde acaba la primera.
    assert fs[0]["t_fin"] == fs[1]["t_inicio"]


# --- repartir ---------------------------------------------------------------

def _frases(n: int, dur: float = 3.0, silencio: float = 0.4) -> list[dict]:
    """Frases con el silencio que de verdad hay entre una y la siguiente: una
    frase empieza con su primera palabra y acaba con la última, así que el
    hueco no es de nadie."""
    return [{"texto": f"frase {i}", "t_inicio": round(i * (dur + silencio), 3),
             "t_fin": round(i * (dur + silencio) + dur, 3)} for i in range(n)]


def test_el_storyboard_decide_cuantas_frases_van_juntas():
    fs = _frases(6)
    grupos, fallos = mf.repartir(fs, [1, 2, 3])
    assert [g["frases"] for g in grupos] == [[0], [1, 2], [3, 4, 5]]
    assert not any(fallos.values())


def test_no_se_queda_ninguna_frase_fuera():
    fs = _frases(7)
    grupos, fallos = mf.repartir(fs, [2, 2])
    assert [i for g in grupos for i in g["frases"]] == list(range(7))
    assert fallos["frases_sueltas"] == 3


def test_un_plano_gloton_deja_sitio_a_los_que_vienen_detras():
    """Si el primero se lleva cinco de seis frases, los dos siguientes se
    quedan sin audio. Se le recorta para que cada plano tenga algo."""
    fs = _frases(6)
    grupos, _ = mf.repartir(fs, [5, 1, 1])
    assert {g["plano"] for g in grupos} == {0, 1, 2}
    assert all(g["frases"] for g in grupos)


def test_sobran_planos_cuando_no_hay_frases_para_todos():
    fs = _frases(2)
    grupos, fallos = mf.repartir(fs, [1, 1, 1, 1])
    assert len(grupos) == 2
    assert fallos["planos_sobrantes"] == 2


def test_una_escena_demasiado_corta_se_funde_con_la_anterior():
    fs = _frases(3, dur=1.0)          # un segundo por frase
    grupos, fallos = mf.repartir(fs, [1, 1, 1])
    assert len(grupos) == 1
    assert fallos["grupo_corto"] == 2


def test_la_primera_corta_se_pega_a_la_siguiente_y_manda_su_plano():
    fs = [{"texto": "ya", "t_inicio": 0.0, "t_fin": 0.8},
          {"texto": "y esto dura", "t_inicio": 0.8, "t_fin": 6.0}]
    grupos, _ = mf.repartir(fs, [1, 1])
    assert len(grupos) == 1 and grupos[0]["plano"] == 0
    assert grupos[0]["frases"] == [0, 1]


def test_un_plano_larguisimo_se_parte_en_tomas_que_continuan():
    fs = _frases(4, dur=6.0)          # 24 segundos en un solo plano
    grupos, fallos = mf.repartir(fs, [4])
    assert len(grupos) > 1
    assert fallos["grupo_largo"] == 1
    # Todas salen del mismo plano, y las de después de la primera continúan.
    assert {g["plano"] for g in grupos} == {0}
    assert [g.get("sigue") for g in grupos[1:]] == [True] * (len(grupos) - 1)


def test_el_reparto_cubre_el_audio_entero():
    """Lo que no puede pasar: que los clips sumen menos que la voz. El montaje
    los encadena, así que cada segundo que falte adelanta todo lo que viene
    detrás y el vídeo se va despegando de lo que se está diciendo."""
    fs = _frases(9)
    fin = 32.0                       # el audio sigue un poco tras la última
    segs = mf.segmentos(fs, mf.repartir(fs, [2, 1, 3, 3])[0], fin)
    assert segs[0]["t_inicio"] == 0.0
    assert segs[-1]["t_fin"] == fin
    # Sin huecos ni solapes: el corte de una escena es el principio de la otra.
    assert all(a["t_fin"] == b["t_inicio"] for a, b in zip(segs, segs[1:]))
    assert sum(s["t_fin"] - s["t_inicio"] for s in segs) == fin


def test_la_escena_empieza_donde_empieza_lo_que_dice():
    """El silencio entre dos frases se lo queda la escena que viene antes, no
    la siguiente: así el corte cae justo cuando arranca la frase nueva."""
    fs = _frases(2, dur=3.0, silencio=1.0)
    segs = mf.segmentos(fs, [{"plano": 0, "frases": [0]},
                             {"plano": 1, "frases": [1]}], 7.0)
    assert segs[0]["t_fin"] == fs[1]["t_inicio"] == 4.0


def test_el_texto_de_la_escena_es_el_de_sus_frases():
    fs = _frases(3)
    segs = mf.segmentos(fs, [{"plano": 0, "frases": [0, 1]}], 10.0)
    assert segs[0]["texto"] == "frase 0 frase 1"


# --- el reloj de los titulares ----------------------------------------------

def test_cada_frase_trae_su_hueco_contado_desde_el_principio_del_clip():
    """El clip de una escena arranca su reloj en cero, así que los tiempos
    absolutos de `palabras.json` hay que traerlos a esa referencia o el titular
    entra fuera de sitio."""
    fs = _frases(3, dur=3.0, silencio=1.0)
    segs = mf.segmentos(fs, [{"plano": 0, "frases": [0]},
                             {"plano": 1, "frases": [1, 2]}], 12.0)
    assert [(f["t0"], f["t1"]) for f in segs[0]["frases"]] == [(0.0, 4.0)]
    # La segunda escena empieza en 4.0: su primera frase arranca ahí mismo y la
    # segunda, cuatro segundos más tarde.
    assert [(f["t0"], f["t1"]) for f in segs[1]["frases"]] == [(0.0, 4.0), (4.0, 8.0)]


def test_el_titular_de_una_frase_dura_hasta_que_empieza_la_siguiente():
    """Si durase solo lo que suena la frase, cada silencio dejaría la pantalla
    sin texto y el vídeo parpadearía."""
    fs = _frases(2, dur=3.0, silencio=1.0)
    segs = mf.segmentos(fs, [{"plano": 0, "frases": [0, 1]}], 7.2)
    primera, segunda = segs[0]["frases"]
    assert primera["t1"] == segunda["t0"]
    assert segunda["t1"] == segs[0]["t_fin"] - segs[0]["t_inicio"]


def test_las_frases_de_la_escena_son_las_suyas_y_en_orden():
    fs = _frases(3)
    segs = mf.segmentos(fs, [{"plano": 0, "frases": [0, 1]}], 10.0)
    assert [f["texto"] for f in segs[0]["frases"]] == ["frase 0", "frase 1"]
