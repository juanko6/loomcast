"""Continuidad de la serie: el contexto del guion y el resumen del episodio."""
import json

import pytest

from backend.repositories import guiones as guiones_repo
from backend.repositories import metadatos as metadatos_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import series as series_repo
from backend.schemas import GuionLineasLLM, GuionLLM, ResumenEpisodioLLM
from backend.services.pipeline import series, texto
from tests import factories as f

pytestmark = pytest.mark.integration

GUION = {"gancho": "Nadie lo vio venir", "frases": ["Una.", "Dos."],
         "cta": "Sigue", "voz_instruct": "voz"}


def _guion_lineas(fake_llm):
    fake_llm.responder(GuionLineasLLM, GuionLineasLLM(
        gancho="La puerta estaba abierta",
        lineas=[{"personaje": "", "texto": "y nadie recordaba haberla abierto"},
                {"personaje": "ANA", "texto": "yo no he sido"}],
        cta="Mañana, el resto",
        voz_instruct="voz",
    ))


# --- contexto de continuidad ------------------------------------------------

def test_un_proyecto_suelto_no_tiene_contexto_de_continuidad(session, dirs_tmp):
    p = f.proyecto(session)
    assert series.contexto_continuidad(p.id) == ""
    assert series.contexto_continuidad(999) == ""


def test_el_guion_de_un_proyecto_sin_serie_pide_lo_mismo_que_siempre(
    session, dirs_tmp, fake_llm
):
    """La prueba que no se puede romper: con series en la base, el guion de un
    vídeo suelto manda al LLM byte a byte la misma petición de antes."""
    f.serie(session)  # hay una serie en la base; este proyecto no es suya
    p = f.proyecto(session, slug="suelto")
    fake_llm.responder(GuionLLM, GuionLLM(**GUION))

    texto.generar_guion(p.id)

    assert fake_llm.llamadas[-1]["user"] == (
        "Idea del video:\n- Título: Una idea\n"
        "- Gancho propuesto: Gancho\n- Resumen: Resumen"
    )
    assert fake_llm.llamadas[-1]["salida"] is GuionLLM


def test_el_primer_episodio_dice_que_es_el_primero(session, dirs_tmp, fake_llm):
    serie = f.serie(session)
    ep = f.episodio(session, serie, numero=1)
    _guion_lineas(fake_llm)

    texto.generar_guion(ep.id)

    user = fake_llm.llamadas[-1]["user"]
    assert "Idea del video:" in user
    assert "CONTINUIDAD DE LA SERIE «La casa de Alicia» — episodio 1" in user
    assert "Es el primer episodio" in user
    # La plantilla de la serie es la que activa las líneas atribuidas.
    assert fake_llm.llamadas[-1]["salida"] is GuionLineasLLM


def test_el_segundo_episodio_lleva_el_reparto_fijo_y_el_resumen_anterior(
    session, dirs_tmp, fake_llm
):
    serie = f.serie(session)
    f.episodio(session, serie, numero=1, titulo="El sobre",
               resumen="Alicia encontró la llave y no se la dio a nadie.")
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")
    # Traído del reparto fijo (reparto_slug lleno) y alguien del casting de este
    # episodio, que no es reparto de la serie.
    f.personaje(session, ep2.id, clave="ANA", nombre="Alicia",
                reparto_slug="ana-narradora")
    f.personaje(session, ep2.id, clave="VECINO", nombre="El vecino",
                ficha="a bald man with a scar")
    _guion_lineas(fake_llm)

    texto.generar_guion(ep2.id)

    user = fake_llm.llamadas[-1]["user"]
    assert "— episodio 2" in user
    # Las claves van tal cual están en el proyecto: son los marcadores con los
    # que se emparejará la voz de cada personaje.
    assert "- {ANA} Alicia: a tall woman with red hair" in user
    assert "VECINO" not in user  # solo el reparto fijo de la serie
    assert "En el episodio anterior (1 — «El sobre»)" in user
    assert "Alicia encontró la llave" in user


def test_un_episodio_cuyo_anterior_no_se_cerro_no_se_inventa_lo_que_paso(
    session, dirs_tmp, fake_llm
):
    serie = f.serie(session)
    f.episodio(session, serie, numero=1)  # sin resumen
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")
    _guion_lineas(fake_llm)

    texto.generar_guion(ep2.id)

    user = fake_llm.llamadas[-1]["user"]
    assert "No hay resumen del episodio anterior" in user


def test_el_titulo_publicado_gana_al_de_la_idea_en_la_continuidad(
    session, dirs_tmp, fake_llm
):
    serie = f.serie(session)
    ep1 = f.episodio(session, serie, numero=1, titulo="Episodio 1",
                     resumen="Pasó algo.")
    metadatos_repo.crear(session, ep1.id, {
        "youtube": {"titulo": "La llave que no abría nada",
                    "descripcion": "d", "etiquetas": []},
        "tiktok": {"descripcion": "t"}})
    session.commit()
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")
    _guion_lineas(fake_llm)

    texto.generar_guion(ep2.id)

    assert "«La llave que no abría nada»" in fake_llm.llamadas[-1]["user"]


# --- resumen del episodio ---------------------------------------------------

def test_generar_resumen_guarda_el_texto_y_no_toca_el_estado(
    session, dirs_tmp, fake_llm
):
    """El resumen cierra el episodio de cara a la serie, no es una etapa más de
    la producción del vídeo: `avanzar_estado` no se toca."""
    serie = f.serie(session)
    ep = f.episodio(session, serie, numero=1)
    guiones_repo.crear(session, ep.id, GUION)
    session.commit()
    fake_llm.responder(ResumenEpisodioLLM, ResumenEpisodioLLM(
        resumen="  Alicia encuentra la llave y la esconde. Nadie sabe de quién es.  "))

    log = series.generar_resumen_episodio(ep.id)

    assert "episodio 1" in log
    session.expire_all()
    p = proyectos_repo.obtener(session, ep.id)
    assert p.resumen_episodio.startswith("Alicia encuentra la llave")
    assert p.estado == "IDEA"


def test_el_resumen_arrastra_lo_que_seguia_abierto(session, dirs_tmp, fake_llm):
    serie = f.serie(session)
    f.episodio(session, serie, numero=1, resumen="Alicia encontró la llave.")
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")
    guiones_repo.crear(session, ep2.id, GUION)
    session.commit()
    fake_llm.responder(ResumenEpisodioLLM,
                       ResumenEpisodioLLM(resumen="x" * 50))

    series.generar_resumen_episodio(ep2.id)

    user = fake_llm.llamadas[-1]["user"]
    assert "Resumen del episodio anterior:\nAlicia encontró la llave." in user
    assert "Nadie lo vio venir" in user  # el guion narrado de este episodio


def test_el_resumen_de_un_proyecto_suelto_o_sin_guion_falla(
    session, dirs_tmp, fake_llm
):
    suelto = f.proyecto(session)
    with pytest.raises(ValueError, match="no es un episodio"):
        series.generar_resumen_episodio(suelto.id)

    ep = f.episodio(session, f.serie(session), numero=1)
    with pytest.raises(ValueError, match="guion"):
        series.generar_resumen_episodio(ep.id)

    with pytest.raises(ValueError, match="no existe"):
        series.generar_resumen_episodio(999)
    assert fake_llm.llamadas == []


def test_resumen_pendiente_solo_para_episodios_sin_cerrar(session, dirs_tmp):
    serie = f.serie(session)
    assert series.resumen_pendiente(f.proyecto(session).id) is False
    assert series.resumen_pendiente(f.episodio(session, serie, numero=1).id) is True
    cerrado = f.episodio(session, serie, numero=2, slug="ep-2", resumen="Pasó.")
    assert series.resumen_pendiente(cerrado.id) is False
    assert series.resumen_pendiente(999) is False


# --- encadenado de la cola --------------------------------------------------

@pytest.mark.parametrize("armado", ["armar_video", "armar_estatico"])
def test_al_armar_el_video_de_un_episodio_se_encola_su_resumen(
    session, dirs_tmp, armado
):
    """Es cuando el episodio está de verdad cerrado, así que el siguiente nace
    con continuidad sin que nadie se acuerde de pedirla."""
    from backend.workers import queue

    ep = f.episodio(session, f.serie(session), numero=1)
    assert queue._encadenado(armado, ep.id) == "generar_resumen_episodio"


@pytest.mark.parametrize("armado", ["armar_video", "armar_estatico"])
def test_el_armado_de_un_video_suelto_no_encadena_nada(session, dirs_tmp, armado):
    from backend.workers import queue

    suelto = f.proyecto(session)
    assert queue._encadenado(armado, suelto.id) is None


def test_un_episodio_ya_cerrado_no_se_resume_otra_vez_al_rearmar(session, dirs_tmp):
    from backend.workers import queue

    ep = f.episodio(session, f.serie(session), numero=1, resumen="Pasó esto.")
    assert queue._encadenado("armar_video", ep.id) is None


def test_las_cadenas_fijas_siguen_igual(session, dirs_tmp):
    from backend.workers import queue

    suelto = f.proyecto(session)
    assert queue._encadenado("generar_voz", suelto.id) == "generar_subtitulos"
    assert queue._encadenado("generar_clips", suelto.id) == "armar_video"
    assert queue._encadenado("regenerar_imagen", suelto.id) is None


# --- las otras plantillas no se enteran -------------------------------------

@pytest.mark.parametrize("plantilla", ["curiosidades", "drama", "historia"])
def test_solo_la_plantilla_de_serie_pide_el_guion_con_lineas(plantilla):
    from backend.repositories import plantillas as plantillas_repo

    assert plantillas_repo.cargar(plantilla)["formato_guion"] != "lineas"
    assert plantillas_repo.cargar("serie")["formato_guion"] == "lineas"
    assert texto.ESQUEMA_GUION["lineas"] is GuionLineasLLM


def test_el_guion_de_un_episodio_normaliza_las_claves_de_las_lineas(
    session, dirs_tmp, fake_llm
):
    """Lo que escriba el LLM al atribuir una línea tiene que casar con la clave
    del personaje, o esa línea se quedaría sin su voz."""
    ep = f.episodio(session, f.serie(session), numero=1)
    fake_llm.responder(GuionLineasLLM, GuionLineasLLM(
        gancho="La puerta estaba abierta",
        lineas=[{"personaje": " ana ", "texto": "yo no he sido"},
                {"personaje": "", "texto": "y la casa siguió callada"}],
        cta="Mañana, el resto",
        voz_instruct="voz",
    ))

    texto.generar_guion(ep.id)

    session.expire_all()
    guion = json.loads(guiones_repo.ultimo(session, ep.id).contenido)
    assert [x["personaje"] for x in guion["lineas"]] == ["ANA", ""]
    assert guiones_repo.tramos(guion) == [
        ("", "La puerta estaba abierta"),
        ("ANA", "yo no he sido"),
        ("", "y la casa siguió callada Mañana, el resto"),
    ]


def test_la_serie_no_tiene_estado_de_produccion(session, dirs_tmp):
    """El ciclo IDEA → … → FINAL es de cada episodio. Dos episodios de la misma
    serie pueden estar en puntos distintos y eso es lo normal."""
    serie = f.serie(session)
    ep1 = f.episodio(session, serie, numero=1)
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")
    from backend.models import avanzar_estado

    avanzar_estado(proyectos_repo.obtener(session, ep1.id), "FINAL")
    session.commit()

    session.expire_all()
    estados = [p.estado for p in series_repo.episodios(session, serie.id)]
    assert estados == ["FINAL", "IDEA"]
    assert not hasattr(series_repo.obtener(session, serie.id), "estado")
    assert proyectos_repo.obtener(session, ep2.id).estado == "IDEA"
