import pytest

from backend.services import musica_combos as mc


@pytest.mark.parametrize("entrada,esperado", [
    ("e minor", "E minor"),
    ("Eb MAJOR", "Eb major"),
    ("A-minor", "A minor"),
    ("Am", "A minor"),
    ("F#min", "F# minor"),
    ("C major scale", "C major"),
    ("C", "C major"),
    ("basura", mc.KEYSCALE_DEFECTO),
    (None, mc.KEYSCALE_DEFECTO),
    (42, mc.KEYSCALE_DEFECTO),
])
def test_normalizar_keyscale(entrada, esperado):
    assert mc.normalizar_keyscale(entrada) == esperado


def test_normalizar_bpm_acota_y_tolera_basura():
    assert mc.normalizar_bpm("90") == 90
    assert mc.normalizar_bpm(10**6) == mc.BPM_MAX
    assert mc.normalizar_bpm(-5) == mc.BPM_MIN
    assert mc.normalizar_bpm("rápido") == mc.BPM_DEFECTO
    assert mc.normalizar_bpm(None) == mc.BPM_DEFECTO


def test_normalizar_timesig_e_idioma_caen_al_defecto():
    assert mc.normalizar_timesig("17") == mc.TIMESIG_DEFECTO
    assert mc.normalizar_idioma("  ZZ ") == mc.IDIOMA_DEFECTO
    assert mc.normalizar_idioma(" ES ") == "es"
