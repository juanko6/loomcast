from backend.services.pipeline.subtitulos import _bloques, _fmt_srt


def _w(texto, start, end):
    return {"word": texto, "start": start, "end": end}


def test_fmt_srt():
    assert _fmt_srt(0) == "00:00:00,000"
    assert _fmt_srt(3661.5) == "01:01:01,500"
    assert _fmt_srt(59.9996) == "00:01:00,000"  # el redondeo propaga el acarreo


def test_bloques_corta_por_max_palabras():
    ws = [_w(f" p{i}", i * 0.2, i * 0.2 + 0.1) for i in range(5)]
    bs = _bloques(ws, 2)
    assert [b["texto"] for b in bs] == ["p0 p1", "p2 p3", "p4"]


def test_bloques_corta_en_puntuacion_fuerte_y_pausa_larga():
    ws = [_w(" hola", 0, .3), _w(" mundo.", .4, .8), _w(" otra", .9, 1.2),
          _w(" cosa", 2.5, 2.8)]  # hueco de 1,3 s antes de "cosa"
    bs = _bloques(ws, 10)
    assert [b["texto"] for b in bs] == ["hola mundo.", "otra", "cosa"]
    assert bs[0]["start"] == 0 and bs[0]["end"] == .8


def test_bloques_vacio():
    assert _bloques([], 3) == []
