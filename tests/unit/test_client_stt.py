"""El cliente de transcripción: se puede cortar entre segmentos de Whisper."""
import pytest

from backend import parada
from backend.clients import stt


class Palabra:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class Segmento:
    def __init__(self, text, words=None):
        self.text, self.words = text, words


class ModeloFalso:
    """faster-whisper devuelve un generador perezoso: cada vuelta decodifica un
    segmento. `al_llegar` se ejecuta tras entregar ese índice."""

    def __init__(self, segmentos, al_llegar=None):
        self.segmentos, self.al_llegar = segmentos, al_llegar or {}
        self.pedidos = []

    def transcribe(self, ruta, **kw):
        self.pedidos.append(kw)

        def generador():
            for i, s in enumerate(self.segmentos):
                yield s
                if i in self.al_llegar:
                    self.al_llegar[i]()

        return generador(), None


@pytest.fixture(autouse=True)
def bandera_limpia():
    yield
    parada.limpiar()


def test_transcribir_junta_texto_y_palabras(monkeypatch, tmp_path):
    modelo = ModeloFalso([
        Segmento(" Hola", [Palabra(" Hola", 0.0, 0.4)]),
        Segmento(" mundo.", [Palabra(" mundo.", 0.5, 0.9)]),
    ])
    monkeypatch.setattr(stt, "_cargar", lambda: modelo)

    r = stt.transcribir(tmp_path / "a.wav", palabras=True)

    assert r["texto"] == "Hola mundo."
    assert [w["word"] for w in r["palabras"]] == [" Hola", " mundo."]
    assert modelo.pedidos[0]["word_timestamps"] is True


def test_sin_palabras_no_pide_timestamps(monkeypatch, tmp_path):
    modelo = ModeloFalso([Segmento(" Hola")])
    monkeypatch.setattr(stt, "_cargar", lambda: modelo)

    r = stt.transcribir(tmp_path / "a.wav")

    assert r["palabras"] == [] and modelo.pedidos[0]["word_timestamps"] is False


def test_parar_a_mitad_abandona_la_transcripcion(monkeypatch, tmp_path):
    """Sin esto habría que esperar a que Whisper acabe el audio entero."""
    parada.iniciar(1)
    modelo = ModeloFalso(
        [Segmento(" Hola"), Segmento(" mundo."), Segmento(" Adiós")],
        al_llegar={0: lambda: parada.marcar(1)},
    )
    monkeypatch.setattr(stt, "_cargar", lambda: modelo)

    with pytest.raises(parada.Parado, match="transcribiendo"):
        stt.transcribir(tmp_path / "a.wav", palabras=True)


def test_si_ya_se_pidio_parar_no_se_carga_el_modelo(monkeypatch, tmp_path, parada_pedida):
    def no_deberia():
        raise AssertionError("no hay que cargar Whisper si ya se pidió parar")

    monkeypatch.setattr(stt, "_cargar", no_deberia)

    with pytest.raises(parada.Parado, match="antes de transcribir"):
        stt.transcribir(tmp_path / "a.wav")
