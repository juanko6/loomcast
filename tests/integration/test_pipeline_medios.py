import json

import pytest

from backend.repositories import galeria as galeria_repo
from backend.repositories import ideas as ideas_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import temas as temas_repo
from backend.services.pipeline import imagen_libre, quitar_fondo, subtitulos

pytestmark = pytest.mark.integration


def test_quitar_fondo_escribe_final_y_marca_estado(session, fake_fondo, dirs_tmp):
    img = galeria_repo.crear(session, "quitarfondo", "x", 64, 64)
    session.commit()
    fuente = imagen_libre.ruta_fuente(img.id)
    fuente.parent.mkdir(parents=True)
    fuente.write_bytes(b"png")

    assert quitar_fondo.quitar_fondo(img.id) == "Fondo eliminado"

    assert fake_fondo.llamadas == [(fuente, imagen_libre.ruta_final(img.id))]
    assert imagen_libre.ruta_final(img.id).exists()
    session.expire_all()
    assert galeria_repo.obtener(session, img.id).estado == "final"


def test_quitar_fondo_sin_origen_falla(session, fake_fondo, dirs_tmp):
    img = galeria_repo.crear(session, "quitarfondo", "x", 64, 64)
    session.commit()
    with pytest.raises(ValueError, match="origen"):
        quitar_fondo.quitar_fondo(img.id)
    assert fake_fondo.llamadas == []


def _proyecto(session):
    tema = temas_repo.crear(session, "t", "curiosidades")
    session.flush()
    idea = ideas_repo.crear(session, tema.id, "t", "g", "r")
    session.flush()
    p = proyectos_repo.crear(session, idea.id, "demo", "curiosidades")
    session.commit()
    return p.id


def test_generar_subtitulos_escribe_srt_y_palabras(session, fake_stt, dirs_tmp):
    pid = _proyecto(session)
    base = dirs_tmp["proyectos"] / "demo"
    base.mkdir()
    (base / "voz.wav").write_bytes(b"wav")

    log = subtitulos.generar_subtitulos(pid)

    assert fake_stt.llamadas == [{"audio": base / "voz.wav", "palabras": True}]
    assert json.loads((base / "palabras.json").read_text())[0]["word"] == " Hola"
    srt = (base / "subtitulos.srt").read_text()
    assert "00:00:00,000 --> 00:00:00,900\nHola mundo." in srt
    assert "Adiós" in srt
    assert log.startswith("2 bloques")
    session.expire_all()
    assert proyectos_repo.obtener(session, pid).estado == "SUBTITULOS"


def test_generar_subtitulos_sin_voz_falla(session, fake_stt, dirs_tmp):
    pid = _proyecto(session)
    with pytest.raises(ValueError, match="voz"):
        subtitulos.generar_subtitulos(pid)
    assert fake_stt.llamadas == []


def test_generar_subtitulos_sin_palabras_falla(session, fake_stt, dirs_tmp):
    pid = _proyecto(session)
    base = dirs_tmp["proyectos"] / "demo"
    base.mkdir()
    (base / "voz.wav").write_bytes(b"wav")
    fake_stt.palabras = []
    with pytest.raises(ValueError, match="palabras"):
        subtitulos.generar_subtitulos(pid)
