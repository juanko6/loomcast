import json

import pytest

from backend.repositories import guiones as guiones_repo
from backend.repositories import personajes as personajes_repo
from backend.schemas import CastingLLM, PersonajeLLM
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


def test_el_casting_sabe_quien_habla_en_el_guion(session, fake_llm):
    """El texto narrado no lleva marcas de quién dice cada cosa —es lo que se
    oye—, así que quien solo existe porque tiene líneas no se vería. Y la clave
    tiene que ser la suya: es con la que la etapa de voz le busca voz."""
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, {"gancho": "G", "cta": "C", "lineas": [
        {"personaje": "", "texto": "El vaso cayó al suelo."},
        # Sin dueño y con el nombre delante: lo rescata `tramos`, así que el
        # casting se entera igual.
        {"personaje": "", "texto": "MARTA: ¿Quién ha tocado la puerta?"},
        {"personaje": "CARLOS", "texto": "Nadie debería estar aquí."},
    ]})
    session.commit()
    fake_llm.responder(CastingLLM, {"personajes": [
        {"clave": "MARTA", "nombre": "Marta", "ficha": FICHA}]})

    casting.generar_casting(p.id)

    user = fake_llm.llamadas[-1]["user"]
    assert "exactly this clave: CARLOS, MARTA" in user
    # Y el nombre no viaja dentro del texto del guion, que es lo que se narra.
    assert "MARTA:" not in user.split("Characters with spoken lines")[0]


def test_sin_lineas_el_casting_pregunta_como_siempre(session, proy, fake_llm):
    """Un guion de frases o de narración continua no tiene a quién atribuir
    nada: la petición es la de siempre, sin bloque de más."""
    fake_llm.responder(CastingLLM, {"personajes": []})
    casting.generar_casting(proy)
    assert "Characters with spoken lines" not in fake_llm.llamadas[-1]["user"]


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


# --- persona u objeto ------------------------------------------------------
# El reparto admite objetos a propósito, pero el encuadre del retrato era de
# persona para todos: a un mapa descrito con "no humans are visible" le pintaba
# una cara encima, que es lo que se vio el 2026-10-19 con la plantilla historia.

FICHA_MAPA = (
    "a large worn tactical map spread on a wooden table with faded blue lines, "
    "black ink dots marking villages and smudged pencil corrections showing "
    "erased street names, no humans are visible"
)


# Fichas tal cual las escribió el LLM en este proyecto, con el tipo que el
# modelo les puso: "persona" a todas, incluidas las cuatro que no lo son. Son el
# caso real que hay que acertar sin hacerle caso.
FICHAS_REALES = [
    ("ARTHUR", "a gaunt British intelligence officer in his late thirties with pale "
     "anxious skin, short cropped dark brown hair, tired grey eyes and ink-stained "
     "fingertips, wearing a rumpled olive wool greatcoat", "persona"),
    ("MAPA", FICHA_MAPA, "objeto"),
    # Sin piel, pelo ni ojos: lo salvan "male" y la edad aparente.
    ("BUZO", "a rugged spanish male diver in his late thirties with a sturdy build, "
     "wearing a professional matte black scuba suit with reinforced padding", "persona"),
    ("COFRE", "an 18th-century wooden treasure chest, rectangular and waist-high, "
     "constructed from dark weathered oak planks with rusted iron hinges and straps, "
     "featuring a prominent brass lock", "objeto"),
    ("CODIGO", "a translucent and ethereal digital entity, composed of shimmering neon "
     "green and electric blue binary code fragments, flickering with glitchy "
     "distortions", "objeto"),
    ("MOTOROLA", "a bulky beige early 1980s brick mobile phone with a thick rectangular "
     "body, a small red LED numeric display, a black antenna and a row of dark rubber "
     "buttons", "objeto"),
    ("ROBOT", "a vintage 1970s industrial research robot with a boxy metallic chassis, "
     "exposed internal wiring and visible cables", "objeto"),
]


@pytest.mark.parametrize("clave,ficha,esperado", FICHAS_REALES)
def test_el_tipo_sale_de_la_ficha_aunque_el_llm_diga_persona(clave, ficha, esperado):
    assert casting.normalizar_tipo("persona", ficha) == esperado


@pytest.mark.parametrize("tipo_llm,ficha,esperado", [
    ("objeto", "a wooden fishing boat with torn sails", "objeto"),
    ("persona", "a woman in her forties with weathered hands, wearing wool", "persona"),
    ("persona", FICHA_MAPA, "objeto"),
    # Tipo ausente o raro con una ficha de persona clara: persona.
    ("", "a tall man with a grey beard, wearing a leather apron", "persona"),
    ("cosa", "a tall man with a grey beard, wearing a leather apron", "persona"),
    # Palabras completas: "chair" lleva "hair" dentro y "human" lleva "man".
    ("", "a wooden chair with a woven straw seat", "objeto"),
    ("", "a bronze bust of a human figure, green with age", "objeto"),
    # Una sola señal: ahí sí desempata el LLM, que para eso se le pregunta.
    ("objeto", "a weathered ship's figurehead carved as a woman", "objeto"),
    ("persona", "a diver wearing a black wetsuit", "persona"),
    # Sin edad, sin rasgos, sin género y sin ropa no hay de dónde agarrarse: el
    # prompt obliga a describir esas cosas en una persona, así que una ficha que
    # no las trae se trata como objeto.
    ("persona", "a diver in a black wetsuit", "objeto"),
    # Sin ficha no hay nada que leer.
    ("", "", "objeto"),
])
def test_normalizar_tipo(tipo_llm, ficha, esperado):
    assert casting.normalizar_tipo(tipo_llm, ficha) == esperado


def test_el_casting_guarda_el_tipo_de_cada_miembro(session, dirs_tmp, fake_llm):
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, {"gancho": "G", "frases": ["f"], "cta": "C"})
    session.commit()
    fake_llm.responder(CastingLLM, CastingLLM(personajes=[
        PersonajeLLM(clave="VIUDA", nombre="la viuda", tipo="persona",
                     ficha="a woman in her fifties with grey hair, wearing black wool"),
        PersonajeLLM(clave="MAPA", nombre="el mapa", tipo="persona", ficha=FICHA_MAPA),
    ]))

    log = casting.generar_casting(p.id)

    session.expire_all()
    tipos = {x.clave: x.tipo for x in personajes_repo.por_proyecto(session, p.id)}
    assert tipos == {"VIUDA": "persona", "MAPA": "objeto"}
    assert "MAPA (objeto)" in log


def test_regenerar_el_casting_conserva_a_los_traidos_del_reparto(session, proy, fake_llm):
    """Perderlos sería malo: el usuario los eligió a mano, su retrato ya está
    copiado en el proyecto y su marcador puede estar escrito en los prompts."""
    f.personaje(session, proy, clave="NARRADOR", nombre="El narrador",
                ficha="a grey-haired man with a deep voice",
                reparto_slug="el-narrador")
    f.personaje(session, proy, clave="EXTRA", nombre="Un extra", ficha=FICHA)
    fake_llm.responder(CastingLLM, {"personajes": [
        {"clave": "LUIS", "nombre": "Luis", "ficha": FICHA}]})

    log = casting.generar_casting(proy)

    assert log == "2 personajes fijados (NARRADOR (del reparto), LUIS)"
    session.expire_all()
    ps = personajes_repo.por_proyecto(session, proy)
    # El del reparto va primero y con su ficha intacta; el del casting anterior,
    # que nació aquí, se fue como siempre.
    assert [(p.clave, p.orden) for p in ps] == [("NARRADOR", 0), ("LUIS", 1)]
    assert ps[0].ficha == "a grey-haired man with a deep voice"


def test_el_del_reparto_gana_la_clave_al_que_acaba_de_escribir_el_llm(session, proy, fake_llm):
    """Conservarlo no es a ciegas: si el LLM escribe a alguien con la misma
    clave, manda el del reparto, porque su ficha es la que no deriva."""
    f.personaje(session, proy, clave="ANA", ficha="a tall woman with red hair",
                reparto_slug="ana-narradora")
    fake_llm.responder(CastingLLM, {"personajes": [
        {"clave": "ana", "nombre": "Ana", "ficha": "a short blonde teenager"},
        {"clave": "luis", "nombre": "Luis", "ficha": FICHA}]})

    assert casting.generar_casting(proy) == "2 personajes fijados (ANA (del reparto), LUIS)"

    session.expire_all()
    ps = personajes_repo.por_proyecto(session, proy)
    assert [p.clave for p in ps] == ["ANA", "LUIS"]
    assert ps[0].ficha == "a tall woman with red hair"


def test_un_casting_vacio_no_se_lleva_a_los_del_reparto(session, proy, fake_llm):
    f.personaje(session, proy, reparto_slug="ana-narradora")
    fake_llm.responder(CastingLLM, {"personajes": []})
    assert casting.generar_casting(proy) == "1 personajes fijados (ANA (del reparto))"
