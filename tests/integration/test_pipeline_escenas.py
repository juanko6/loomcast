import json

import pytest

from backend.repositories import escenas as escenas_repo
from backend.repositories import guiones as guiones_repo
from backend.repositories import metadatos as metadatos_repo
from backend.repositories import proyectos as proyectos_repo
from backend.schemas import EscenaLLM
from backend.services.pipeline import escenas
from tests import factories as f

pytestmark = pytest.mark.integration

PROMPT = "cinematic shot of a lighthouse at dusk"
MOV = "slow push in towards the lighthouse"


@pytest.fixture
def listo(session, dirs_tmp):
    """Proyecto con guion y palabras.json: 8 palabras en 7,5 s → 2 escenas."""
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, {"gancho": "G", "frases": ["f"], "cta": "C"})
    metadatos_repo.crear(session, p.id, {"youtube": {"titulo": "Titulo"}})
    session.commit()
    base = dirs_tmp["proyectos"] / "demo"
    base.mkdir()
    (base / "palabras.json").write_text(json.dumps(
        [{"word": f" p{i}", "start": i * 1.0, "end": i * 1.0 + 0.5} for i in range(8)]))
    return p.id


def test_generar_escenas_guarda_una_por_segmento_y_avanza_estado(session, listo, fake_llm):
    fake_llm.responder(EscenaLLM, EscenaLLM(prompt=PROMPT, prompt_movimiento=MOV))

    log = escenas.generar_escenas(listo)

    assert log.startswith("2 escenas")
    session.expire_all()
    es = escenas_repo.por_proyecto(session, listo)
    assert [e.orden for e in es] == [0, 1]
    assert es[0].texto == "p0 p1 p2 p3" and es[0].prompt == PROMPT and es[0].prompt_movimiento == MOV
    assert (es[0].t_inicio, es[1].t_fin) == (0.0, 7.5)
    assert proyectos_repo.obtener(session, listo).estado == "ESCENAS"
    assert len(fake_llm.llamadas) == 2
    assert "Titulo" in fake_llm.llamadas[0]["user"] and "p0 p1 p2 p3" in fake_llm.llamadas[0]["user"]


def test_generar_escenas_con_reparto_sustituye_marcadores_y_anota_quien_sale(session, listo, fake_llm):
    f.personaje(session, listo, ficha="a woman in her thirties with dark curls")
    fake_llm.responder(EscenaLLM, EscenaLLM(
        prompt="{ANA} looks at the sea from the cliff", prompt_movimiento="{ANA} turns her head slowly"))

    escenas.generar_escenas(listo)

    session.expire_all()
    e = escenas_repo.por_proyecto(session, listo)[0]
    assert e.personajes == "ANA" and "dark curls" in e.prompt and "{" not in e.prompt
    assert e.prompt_movimiento.startswith("a woman in her thirties turns")
    assert "{ANA}" in fake_llm.llamadas[0]["user"]  # el LLM recibe el reparto


def test_regenerar_escenas_reemplaza_el_set_completo(session, listo, fake_llm):
    f.escenas(session, listo, n=5)
    fake_llm.responder(EscenaLLM, EscenaLLM(prompt=PROMPT, prompt_movimiento=MOV))
    escenas.generar_escenas(listo)
    session.expire_all()
    assert len(escenas_repo.por_proyecto(session, listo)) == 2


def test_generar_escenas_sin_palabras_json_falla(session, listo, fake_llm, dirs_tmp):
    (dirs_tmp["proyectos"] / "demo" / "palabras.json").unlink()
    with pytest.raises(ValueError, match="palabras.json"):
        escenas.generar_escenas(listo)
    assert fake_llm.llamadas == []


def test_generar_escenas_sin_guion_falla(session, dirs_tmp, fake_llm):
    p = f.proyecto(session)
    with pytest.raises(ValueError, match="guion"):
        escenas.generar_escenas(p.id)


def test_generar_escenas_proyecto_inexistente(engine, fake_llm):
    with pytest.raises(ValueError, match="no existe"):
        escenas.generar_escenas(99)


def test_error_del_llm_a_mitad_no_deja_escenas_a_medias(session, listo, fake_llm):
    f.escenas(session, listo, n=3)
    fake_llm.encadenar(EscenaLLM, [EscenaLLM(prompt=PROMPT, prompt_movimiento=MOV)])  # la 2ª llamada falla

    with pytest.raises(AssertionError, match="FakeLLM"):
        escenas.generar_escenas(listo)

    session.expire_all()
    assert len(escenas_repo.por_proyecto(session, listo)) == 3  # las anteriores siguen
