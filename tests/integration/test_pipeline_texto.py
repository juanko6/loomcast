import json

import pytest

from backend.repositories import guiones as guiones_repo
from backend.repositories import ideas as ideas_repo
from backend.repositories import metadatos as metadatos_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import temas as temas_repo
from backend.schemas import (
    DescripcionLLM,
    EtiquetasLLM,
    GuionLLM,
    IdeasLLM,
    TituloLLM,
)
from backend.services.pipeline import texto

pytestmark = pytest.mark.integration


def _tema_con_proyecto(session):
    tema = temas_repo.crear(session, "el espacio", "curiosidades")
    session.flush()
    idea = ideas_repo.crear(session, tema.id, "Titulo idea", "Gancho", "Resumen")
    session.flush()
    p = proyectos_repo.crear(session, idea.id, "proyecto-test", "curiosidades")
    session.commit()
    return tema.id, p.id


def test_generar_ideas_guarda_lo_que_devuelve_el_llm(session, fake_llm):
    tema_id, _ = _tema_con_proyecto(session)
    fake_llm.responder(IdeasLLM, [
        {"titulo": "A", "gancho": "g1", "resumen": "r1"},
        {"titulo": "B", "gancho": "g2", "resumen": "r2"},
    ])

    log = texto.generar_ideas(tema_id)

    assert log == "2 ideas generadas"
    assert "el espacio" in fake_llm.llamadas[0]["user"]
    session.expire_all()
    assert [i.titulo for i in ideas_repo.por_tema(session, tema_id)][-2:] == ["A", "B"]


def test_generar_ideas_tema_inexistente(engine, fake_llm):
    with pytest.raises(ValueError, match="no existe"):
        texto.generar_ideas(999)
    assert fake_llm.llamadas == []


def test_generar_guion_guarda_version_y_avanza_estado(session, fake_llm):
    _, pid = _tema_con_proyecto(session)
    fake_llm.responder(GuionLLM, GuionLLM(
        gancho="Gancho", frases=["Una.", "Dos."], cta="Sigue", voz_instruct="voz"
    ))

    log = texto.generar_guion(pid)

    assert log == "Guion v1 generado"
    session.expire_all()
    assert proyectos_repo.obtener(session, pid).estado == "GUION"
    assert json.loads(guiones_repo.ultimo(session, pid).contenido)["frases"] == ["Una.", "Dos."]


def test_generar_metadatos_encadena_titulo_descripcion_etiquetas(session, fake_llm):
    _, pid = _tema_con_proyecto(session)
    guiones_repo.crear(session, pid, {
        "gancho": "G", "frases": ["f1"], "cta": "C", "voz_instruct": "v"})
    session.commit()
    titulo = "Un título suficientemente largo"
    fake_llm.responder(TituloLLM, TituloLLM(titulo=titulo))
    fake_llm.responder(DescripcionLLM, DescripcionLLM(descripcion="d" * 120))
    fake_llm.responder(EtiquetasLLM, EtiquetasLLM(
        etiquetas=["a", "b", "c", "d", "e"], tiktok="tt"))

    texto.generar_metadatos(pid)

    # La descripción y las etiquetas se piden con el título ya elegido.
    assert [c["salida"] for c in fake_llm.llamadas] == [TituloLLM, DescripcionLLM, EtiquetasLLM]
    assert titulo in fake_llm.llamadas[1]["user"]
    session.expire_all()
    meta = json.loads(metadatos_repo.ultimo(session, pid).contenido)
    assert meta["youtube"]["titulo"] == titulo
    assert meta["tiktok"] == {"descripcion": "tt"}
    assert proyectos_repo.obtener(session, pid).estado == "METADATOS"


def test_generar_metadatos_sin_guion_falla(session, fake_llm):
    _, pid = _tema_con_proyecto(session)
    with pytest.raises(ValueError, match="guion"):
        texto.generar_metadatos(pid)
