import json

import pytest

from backend.repositories import guiones as guiones_repo
from backend.repositories import ideas as ideas_repo
from backend.repositories import metadatos as metadatos_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import temas as temas_repo
from backend.repositories import plantillas as plantillas_repo
from backend.schemas import (
    DescripcionLLM,
    EtiquetasLLM,
    GuionLineasLLM,
    GuionLLM,
    GuionNarracionLLM,
    IdeasLLM,
    TituloLLM,
)
from backend.services.pipeline import texto
from tests import factories as f

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


def test_las_ideas_de_una_serie_con_hilo_son_maneras_del_episodio_que_toca(
    session, fake_llm
):
    """Las ocho ideas a ciegas eran la deriva: ocho capítulos escritos de una vez
    sin saber qué había pasado en ninguno. Con hilo se pide uno, el que toca."""
    serie = f.serie(session, premisa="Una casa habitada.")
    f.hilo(session, serie, tramos=3)
    f.episodio(session, serie, numero=1, resumen="Alicia encontró la llave.")
    fake_llm.responder(IdeasLLM, [
        {"titulo": "Por el portal", "gancho": "g1", "resumen": "r1"},
        {"titulo": "Por teléfono", "gancho": "g2", "resumen": "r2"},
    ])

    log = texto.generar_ideas(serie.tema_id)

    assert log == "2 maneras de rodar el episodio 2"
    user = fake_llm.llamadas[-1]["user"]
    assert "el episodio 2" in user
    assert "Alicia encontró la llave." in user
    assert "pasa la cosa 2" in user
    assert "{n_ideas}" not in fake_llm.llamadas[-1]["system"]
    # Y en la lista se ven como lo que son: tres versiones del mismo capítulo.
    session.expire_all()
    assert [i.titulo for i in ideas_repo.por_tema(session, serie.tema_id)][-2:] == [
        "Episodio 2: Por el portal", "Episodio 2: Por teléfono",
    ]


def test_las_ideas_de_una_serie_sin_hilo_son_las_de_siempre(session, fake_llm):
    serie = f.serie(session)
    fake_llm.responder(IdeasLLM, [{"titulo": "A", "gancho": "g", "resumen": "r"}])

    assert texto.generar_ideas(serie.tema_id) == "1 ideas generadas"
    assert fake_llm.llamadas[-1]["user"] == "Tema: La casa de Alicia"


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


def test_generar_guion_de_historia_usa_narracion_y_su_ritmo(session, fake_llm):
    """`historia` cuenta un relato seguido, así que el guion no viene en frases:
    la plantilla cambia el esquema que se le pide al LLM y la duración objetivo."""
    tema = temas_repo.crear(session, "el Titanic", "historia")
    session.flush()
    idea = ideas_repo.crear(session, tema.id, "T", "G", "R")
    session.flush()
    proy = proyectos_repo.crear(session, idea.id, "proyecto-historia", "historia")
    session.commit()
    pid = proy.id
    fake_llm.responder(GuionNarracionLLM, GuionNarracionLLM(
        gancho="Un barco que no vuelve",
        narracion="Y entonces, con la nieve hasta el pecho, siguieron.",
        cta="Nadie volvió a buscarlos",
        voz_instruct="voz",
    ))

    texto.generar_guion(pid)

    assert fake_llm.llamadas[-1]["salida"] is GuionNarracionLLM
    system = fake_llm.llamadas[-1]["system"]
    assert "55 segundos" in system and "{duracion}" not in system
    session.expire_all()
    guion = json.loads(guiones_repo.ultimo(session, pid).contenido)
    assert guion["narracion"].startswith("Y entonces")


@pytest.mark.parametrize("plantilla", ["curiosidades", "drama", "historia"])
def test_las_plantillas_actuales_no_piden_el_guion_con_lineas(plantilla):
    """El formato de líneas atribuidas es opt-in por plantilla y hoy no lo activa
    ninguna: las tres que hay siguen pidiendo al LLM el esquema de siempre, que
    es lo que decide byte a byte lo que sale de esta etapa."""
    formato = plantillas_repo.cargar(plantilla)["formato_guion"]
    esquema = texto.ESQUEMA_GUION.get(formato, GuionLLM)
    assert esquema is (GuionNarracionLLM if formato == "narracion" else GuionLLM)
    assert esquema is not GuionLineasLLM


def test_una_plantilla_con_lineas_pide_el_esquema_atribuido_y_normaliza_las_claves(
    session, fake_llm, monkeypatch
):
    """Así se activa el formato nuevo: una clave en plantilla.json. La clave del
    personaje pasa por el normalizador del reparto, porque es el marcador con el
    que el casting lo encontrará luego en el guion."""
    _, pid = _tema_con_proyecto(session)
    real = plantillas_repo.cargar
    monkeypatch.setattr(
        plantillas_repo, "cargar",
        lambda nombre: {**real(nombre), "formato_guion": "lineas"},
    )
    fake_llm.responder(GuionLineasLLM, GuionLineasLLM(
        gancho="Nadie lo vio venir",
        lineas=[{"personaje": " ana ", "texto": "yo estaba allí"},
                {"personaje": "", "texto": "y la historia siguió"}],
        cta="Cuéntalo tú",
        voz_instruct="voz",
    ))

    texto.generar_guion(pid)

    assert fake_llm.llamadas[-1]["salida"] is GuionLineasLLM
    session.expire_all()
    guion = json.loads(guiones_repo.ultimo(session, pid).contenido)
    assert guion["lineas"] == [
        {"personaje": "ANA", "texto": "yo estaba allí"},
        {"personaje": "", "texto": "y la historia siguió"},
    ]
    # Y lo que se narra (y lo que leen escenas, música y metadatos) sigue siendo
    # el texto seguido, sin marcas de quién habla.
    assert guiones_repo.texto_narrado(guion) == (
        "Nadie lo vio venir yo estaba allí y la historia siguió Cuéntalo tú")


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
