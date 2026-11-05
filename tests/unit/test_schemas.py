import pytest
from pydantic import ValidationError

from backend.schemas import (
    CastingLLM,
    DescripcionLLM,
    EscenaLLM,
    EtiquetasLLM,
    GuionLineasLLM,
    GuionLLM,
    GuionNarracionLLM,
    IdeaLLM,
    IdeasLLM,
    LineaGuionLLM,
    MusicaPromptLLM,
    PersonajeLLM,
    PersonajeNuevoIn,
    Plantilla,
    TituloLLM,
)

BASE_GUION = {"gancho": "g", "frases": ["f"], "cta": "c", "voz_instruct": "v"}


def test_ideas_exige_al_menos_una_y_campos_no_vacios():
    ok = {"titulo": "t", "gancho": "g", "resumen": "r"}
    assert len(IdeasLLM.model_validate([ok]).root) == 1
    with pytest.raises(ValidationError):
        IdeasLLM.model_validate([])
    for campo in ok:
        with pytest.raises(ValidationError):
            IdeaLLM.model_validate({**ok, campo: ""})
    with pytest.raises(ValidationError):
        IdeaLLM.model_validate({**ok, "titulo": "x" * 201})


@pytest.mark.parametrize("cambio", [
    {"gancho": ""}, {"frases": []}, {"cta": ""}, {"voz_instruct": ""}])
def test_guion_rechaza_vacios(cambio):
    with pytest.raises(ValidationError):
        GuionLLM.model_validate({**BASE_GUION, **cambio})


def test_guion_exige_todos_los_campos():
    with pytest.raises(ValidationError):
        GuionLLM.model_validate({"gancho": "g"})


def test_guion_narracion():
    ok = {"gancho": "g", "narracion": "n", "cta": "c", "voz_instruct": "v"}
    assert GuionNarracionLLM.model_validate(ok).narracion == "n"
    with pytest.raises(ValidationError):
        GuionNarracionLLM.model_validate({**ok, "narracion": ""})


def test_guion_lineas():
    ok = {"gancho": "g", "cta": "c", "voz_instruct": "v",
          "lineas": [{"personaje": "ANA", "texto": "hablo"}, {"texto": "narro"}]}
    g = GuionLineasLLM.model_validate(ok)
    # El personaje es opcional: sin él la línea es del narrador, que es lo
    # normal porque la mayoría del guion la lleva él.
    assert [(x.personaje, x.texto) for x in g.lineas] == [("ANA", "hablo"), ("", "narro")]
    for cambio in ({"lineas": []}, {"gancho": ""}, {"cta": ""}):
        with pytest.raises(ValidationError):
            GuionLineasLLM.model_validate({**ok, **cambio})
    with pytest.raises(ValidationError):
        LineaGuionLLM.model_validate({"texto": ""})


@pytest.mark.parametrize("n,valido", [(9, False), (10, True), (80, True), (81, False)])
def test_titulo_limites(n, valido):
    if valido:
        assert TituloLLM(titulo="x" * n)
    else:
        with pytest.raises(ValidationError):
            TituloLLM(titulo="x" * n)


@pytest.mark.parametrize("n,valido", [(99, False), (100, True), (600, True), (601, False)])
def test_descripcion_limites(n, valido):
    if valido:
        assert DescripcionLLM(descripcion="x" * n)
    else:
        with pytest.raises(ValidationError):
            DescripcionLLM(descripcion="x" * n)


@pytest.mark.parametrize("n,valido", [(4, False), (5, True), (15, True), (16, False)])
def test_etiquetas_cantidad(n, valido):
    datos = {"etiquetas": ["e"] * n, "tiktok": "t"}
    if valido:
        assert EtiquetasLLM.model_validate(datos)
    else:
        with pytest.raises(ValidationError):
            EtiquetasLLM.model_validate(datos)


def test_etiquetas_tiktok_vacio_o_largo():
    for tiktok in ("", "x" * 251):
        with pytest.raises(ValidationError):
            EtiquetasLLM(etiquetas=["e"] * 5, tiktok=tiktok)


def test_casting_acepta_lista_vacia_y_por_defecto():
    assert CastingLLM().personajes == []
    assert CastingLLM(personajes=[]).personajes == []


def test_personaje_ficha_minima_y_clave_maxima():
    ok = {"clave": "ANA", "nombre": "Ana", "ficha": "x" * 20}
    assert PersonajeLLM.model_validate(ok)
    for malo in ({"ficha": "x" * 19}, {"clave": ""}, {"clave": "A" * 25}, {"nombre": ""}):
        with pytest.raises(ValidationError):
            PersonajeLLM.model_validate({**ok, **malo})


def test_escena_prompts_minimos():
    largo = "x" * 20
    assert EscenaLLM(prompt=largo, prompt_movimiento=largo)
    with pytest.raises(ValidationError):
        EscenaLLM(prompt="corto", prompt_movimiento=largo)
    with pytest.raises(ValidationError):
        EscenaLLM(prompt=largo, prompt_movimiento="")


def test_musica_prompt_tiene_valores_por_defecto_musicales():
    m = MusicaPromptLLM(tags="x" * 20)
    assert (m.bpm, m.keyscale, m.timesig, m.idioma, m.lyrics, m.portada) == (
        120, "C major", "4", "es", "", "")
    with pytest.raises(ValidationError):
        MusicaPromptLLM(tags="corto")


def test_musica_prompt_recupera_claves_con_errata():
    # El Qwen 35B en 4 bits escribe "lytics": sin esto el guion se perdía.
    m = MusicaPromptLLM.model_validate(
        {"tags": "x" * 20, "lytics": "[Intro - guitarra]", "bpm": 75})
    assert m.lyrics == "[Intro - guitarra]" and m.bpm == 75
    # Una clave bien escrita no se pisa con otra parecida.
    m = MusicaPromptLLM.model_validate(
        {"tags": "x" * 20, "lyrics": "[A]", "lytics": "[B]"})
    assert m.lyrics == "[A]"
    # Lo que no se parece a nada se sigue ignorando.
    assert MusicaPromptLLM.model_validate({"tags": "x" * 20, "otra": 1}).lyrics == ""


def test_personaje_nuevo_in_clave_obligatoria():
    assert PersonajeNuevoIn(clave="A").nombre == ""
    with pytest.raises(ValidationError):
        PersonajeNuevoIn(clave="")


# --- Plantilla --------------------------------------------------------------

def _plantilla(**cambios):
    base = {
        "nombre": "x", "voz": {"instruct": "i", "language": "Spanish"},
        "estilo_visual": "e", "subtitulos": {}, "ritmo": {"duracion_objetivo_s": 45},
    }
    return {**base, **cambios}


def test_plantilla_minima_aplica_defectos():
    p = Plantilla.model_validate(_plantilla())
    assert p.formato_guion == "frases" and p.subtitulos.max_palabras_por_bloque == 3
    assert p.ritmo.atempo == 1.0 and p.ritmo.duracion_escena_s == 4


def test_plantilla_admite_claves_extra():
    assert Plantilla.model_validate(_plantilla(otra="cosa")).model_extra == {"otra": "cosa"}


@pytest.mark.parametrize("cambios", [
    {"formato_guion": "poema"},
    {"ritmo": {"duracion_objetivo_s": 14}},
    {"ritmo": {"duracion_objetivo_s": 121}},
    {"ritmo": {"duracion_objetivo_s": 45, "atempo": 0.4}},
    {"ritmo": {"duracion_objetivo_s": 45, "atempo": 2.1}},
    {"ritmo": {"duracion_objetivo_s": 45, "duracion_escena_s": 0}},
    {"subtitulos": {"max_palabras_por_bloque": 0}},
    {"subtitulos": {"max_palabras_por_bloque": 9}},
    {"voz": {"instruct": "i"}},
])
def test_plantilla_invalida(cambios):
    with pytest.raises(ValidationError):
        Plantilla.model_validate(_plantilla(**cambios))


def test_plantilla_sin_campos_obligatorios():
    for campo in ("nombre", "voz", "estilo_visual", "subtitulos", "ritmo"):
        datos = _plantilla()
        del datos[campo]
        with pytest.raises(ValidationError):
            Plantilla.model_validate(datos)


def _plantillas_del_repo():
    """En tiempo de colección: parametriza con las plantillas que hay en disco,
    así una nueva entra sola en el test en vez de quedarse sin cubrir."""
    from backend.repositories import plantillas

    return plantillas.listar()


# Los ocho prompts que el pipeline busca por nombre; si falta uno, la etapa
# revienta a mitad de la generación en vez de al cargar la plantilla.
PROMPTS_ESPERADOS = {
    "ideas", "guion", "storyboard", "escena", "casting",
    "titulo", "descripcion", "etiquetas",
}


@pytest.mark.parametrize("nombre", _plantillas_del_repo())
def test_las_plantillas_reales_son_validas(nombre):
    from backend.repositories import plantillas

    pl = plantillas.cargar(nombre)
    assert set(pl["prompts"]) == PROMPTS_ESPERADOS
    # Los huecos que rellena texto.py: si la plantilla no los trae, el prompt
    # llega al LLM pidiendo "{n_ideas} ideas" en vez de un número.
    assert "{n_ideas}" in pl["prompts"]["ideas"]
    for hueco in ("{duracion}", "{min_palabras}", "{max_palabras}"):
        assert hueco in pl["prompts"]["guion"]
