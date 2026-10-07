import json

import pytest

from backend.repositories import guiones as guiones_repo
from backend.repositories import personajes as personajes_repo
from backend.schemas import CastingLLM
from backend.services.pipeline import casting
from tests import factories as f

pytestmark = pytest.mark.integration

FICHA = "a woman in her thirties with dark curls and a red coat"


@pytest.fixture
def proy(session):
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, {"gancho": "G", "frases": ["f"], "cta": "C"})
    session.commit()
    return p.id


@pytest.mark.parametrize("entrada,esperado", [
    ("  a woman   with\ncurls. ", "a woman with curls"),
    ("a man. He has a beard. He wears a hat.", "a man, a beard, a hat"),
    ("a girl. She is tall", "a girl, tall"),
    ("tall woman. Red hair", "tall woman, Red hair"),
    ("", ""),
])
def test_limpiar_ficha(entrada, esperado):
    assert casting._limpiar_ficha(entrada) == esperado


def test_generar_casting_guarda_personajes_normalizados(session, proy, fake_llm):
    fake_llm.responder(CastingLLM, {"personajes": [
        {"clave": "ana lópez", "nombre": " Ana ", "ficha": FICHA + ". She has green eyes"},
        {"clave": "Luis", "nombre": "Luis", "ficha": FICHA}]})

    log = casting.generar_casting(proy)

    assert log == "2 personajes fijados (ANA_LPEZ, LUIS)"
    session.expire_all()
    ps = personajes_repo.por_proyecto(session, proy)
    assert [p.clave for p in ps] == ["ANA_LPEZ", "LUIS"] and ps[0].nombre == "Ana"
    assert ps[0].ficha.endswith("red coat, green eyes") and ps[0].seed


def test_casting_descarta_claves_repetidas_o_vacias(session, proy, fake_llm):
    fake_llm.responder(CastingLLM, {"personajes": [
        {"clave": "ana", "nombre": "A", "ficha": FICHA},
        {"clave": "ANA", "nombre": "B", "ficha": FICHA},
        {"clave": "!!!", "nombre": "C", "ficha": FICHA}]})
    assert casting.generar_casting(proy) == "1 personajes fijados (ANA)"


def test_casting_vacio_es_valido_y_borra_el_reparto_anterior(session, proy, fake_llm):
    f.personaje(session, proy)
    fake_llm.responder(CastingLLM, {"personajes": []})
    assert casting.generar_casting(proy).startswith("Sin personajes recurrentes")
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy) == []


def test_el_casting_recibe_el_guion_y_el_estilo(session, proy, fake_llm):
    fake_llm.responder(CastingLLM, {"personajes": []})
    casting.generar_casting(proy)
    user = fake_llm.llamadas[0]["user"]
    assert "G f C" in user and "Template visual style" in user


def test_casting_sin_guion_o_proyecto_inexistente(session, fake_llm):
    p = f.proyecto(session)
    with pytest.raises(ValueError, match="guion"):
        casting.generar_casting(p.id)
    with pytest.raises(ValueError, match="no existe"):
        casting.generar_casting(99)
    assert fake_llm.llamadas == []


def test_casting_con_plantilla_sin_prompt_de_casting(session, proy, fake_llm, monkeypatch):
    from backend.repositories import plantillas

    monkeypatch.setattr(plantillas, "cargar", lambda n: {"prompts": {}, "estilo_visual": "x"})
    with pytest.raises(ValueError, match="casting.md"):
        casting.generar_casting(proy)
    assert fake_llm.llamadas == []
