"""Continuidad de la serie: el contexto del guion y el resumen del episodio."""
import json

import pytest

from backend.repositories import guiones as guiones_repo
from backend.repositories import hilos as hilos_repo
from backend.repositories import metadatos as metadatos_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import series as series_repo
from backend.schemas import (
    GuionLineasLLM,
    GuionLLM,
    HiloLLM,
    ResumenEpisodioLLM,
)
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


def test_un_canon_de_otra_version_del_guion_esta_pendiente(session, dirs_tmp):
    """Si el guion se edita, el resumen cuenta una versión que ya no existe, y
    lo que miente aquí es canon en el capítulo siguiente."""
    ep = f.episodio(session, f.serie(session), numero=1, resumen="Pasó esto.")
    guiones_repo.crear(session, ep.id, GUION)
    ep.resumen_version = 1
    session.commit()
    assert series.resumen_pendiente(ep.id) is False

    guiones_repo.crear(session, ep.id, GUION)  # v2: lo editaron
    session.commit()
    assert series.resumen_pendiente(ep.id) is True


# --- encadenado de la cola --------------------------------------------------

@pytest.mark.parametrize("armado", ["armar_video", "armar_estatico"])
def test_el_armado_de_un_episodio_ya_no_encadena_su_resumen(
    session, dirs_tmp, armado
):
    """El resumen estuvo encadenado aquí y se fue de aquí: solo depende del
    guion, así que esperar al vídeo metía el render en el camino de la historia.
    Ahora lo pide el autopiloto en cuanto el guion está aprobado."""
    from backend.workers import queue

    ep = f.episodio(session, f.serie(session), numero=1)
    assert queue._encadenado(armado, ep.id) is None


def test_el_canon_se_pide_justo_despues_del_guion(session, dirs_tmp):
    """Lo que antes pasaba al final del montaje: el episodio siguiente ya puede
    escribirse sin esperar un solo segundo de GPU."""
    from backend.services import autopiloto

    ep = f.episodio(session, f.serie(session), numero=1)
    guiones_repo.crear(session, ep.id, GUION)
    session.commit()

    assert autopiloto._que_falta(session, ep, "estatico") == (
        "generar_resumen_episodio"
    )


def test_un_video_suelto_no_pide_canon_nunca(session, dirs_tmp):
    from backend.services import autopiloto

    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, GUION)
    session.commit()

    assert autopiloto._que_falta(session, p, "estatico") == "generar_casting"


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


# --- el hilo ----------------------------------------------------------------

FICHA = ("a tired woman in her late thirties with olive skin, dark hair in a "
         "loose bun and permanent shadows under her eyes, wearing a faded "
         "navy hoodie over supermarket work trousers")

HILO = {
    "premisa": "Alicia hereda una casa en la que ya vive alguien.",
    "pregunta": "¿Quién entraba en la casa por la noche?",
    "destino": "Era su hermano y le deja quedarse.",
    "reparto": [{"clave": "ALICIA", "nombre": "Alicia", "tipo": "persona",
                 "ficha": FICHA}],
    "fuera": ["no aparece la policia"],
    "episodios_recomendados": 4,
    "por_que": "aguanta cuatro giros",
    "tramos": [
        {"titulo": "La llave", "pasa": "encuentra una llave",
         "cambia": "sabe que no está sola"},
        {"titulo": "El ruido", "pasa": "oye pasos", "cambia": "deja de dormir"},
    ],
}


def _hilo_llm(fake_llm, **cambios):
    fake_llm.responder(HiloLLM, HiloLLM(**{**HILO, **cambios}))


def test_el_hilo_sale_de_la_premisa_y_dice_cuantos_episodios(
    session, dirs_tmp, fake_llm
):
    serie = f.serie(session, premisa="Alicia hereda una casa habitada.")
    _hilo_llm(fake_llm)

    assert "Hilo v1" in series.generar_hilo(serie.id)

    guardado = hilos_repo.contenido(session, serie.id)
    assert guardado["destino"] == "Era su hermano y le deja quedarse."
    # Los tramos se numeran por su posición, que es el episodio al que le tocan.
    assert [t["numero"] for t in guardado["tramos"]] == [1, 2]
    # Y la premisa del usuario llega al LLM, que es de donde sale todo.
    assert "Alicia hereda una casa habitada." in fake_llm.llamadas[-1]["user"]


def test_sin_premisa_no_hay_hilo_que_escribir(session, dirs_tmp, fake_llm):
    serie = f.serie(session)
    with pytest.raises(ValueError, match="premisa"):
        series.generar_hilo(serie.id)
    assert fake_llm.llamadas == []


def test_los_episodios_pedidos_mandan_sobre_la_recomendacion(
    session, dirs_tmp, fake_llm
):
    serie = f.serie(session, premisa="Una casa habitada.", episodios=6)
    _hilo_llm(fake_llm)

    series.generar_hilo(serie.id)

    assert "6 episodios" in fake_llm.llamadas[-1]["system"]


def test_replanificar_no_toca_los_tramos_ya_rodados(session, dirs_tmp, fake_llm):
    """Lo hecho no se toca, igual que con el reparto fijo: un capítulo escrito
    no cambia de sitio en el mapa porque el mapa se redibuje."""
    serie = f.serie(session, premisa="Una casa habitada.")
    f.hilo(session, serie, tramos=3)
    f.episodio(session, serie, numero=1, resumen="Alicia encontró la llave.")
    _hilo_llm(fake_llm, tramos=[
        {"titulo": "Nuevo rumbo", "pasa": "pasa otra cosa",
         "cambia": "cambia otra cosa"},
    ])

    assert "replanificado" in series.generar_hilo(serie.id)

    tramos = hilos_repo.tramos(hilos_repo.contenido(session, serie.id))
    assert [t["titulo"] for t in tramos] == ["Tramo 1", "Nuevo rumbo"]
    # Y el LLM recibe lo que de verdad pasó en el rodado, no solo lo planeado.
    user = fake_llm.llamadas[-1]["user"]
    assert "Alicia encontró la llave." in user
    assert "Su tramo decía: pasa la cosa 1" in user


# --- el hilo dentro del guion y del canon -----------------------------------

def test_el_guion_del_episodio_sabe_que_sitio_ocupa(session, dirs_tmp):
    serie = f.serie(session)
    f.hilo(session, serie, tramos=3)
    ep = f.episodio(session, serie, numero=2)

    ctx = series.contexto_continuidad(ep.id)

    assert "TU SITIO EN EL MAPA: episodio 2 de 3" in ctx
    assert "pasa la cosa 2" in ctx
    # Lo que viene detrás se le da para que NO pase hoy.
    assert "todavía NO puede pasar" in ctx
    assert "pasa la cosa 3" in ctx
    assert "nada sobrenatural" in ctx


def test_el_ultimo_episodio_es_el_unico_que_cierra(session, dirs_tmp):
    """El prompt del guion prohíbe resolver la serie, y sin hilo no había manera
    de pedir el capítulo final."""
    serie = f.serie(session)
    f.hilo(session, serie, tramos=2)

    ctx = series.contexto_continuidad(f.episodio(session, serie, numero=2).id)

    assert "ÚLTIMO EPISODIO" in ctx


def test_un_episodio_que_se_sale_del_mapa_lo_dice(session, dirs_tmp):
    serie = f.serie(session)
    f.hilo(session, serie, tramos=2)

    ctx = series.contexto_continuidad(f.episodio(session, serie, numero=3).id)

    assert "se sale del mapa" in ctx
    assert "TU SITIO EN EL MAPA: episodio" not in ctx


def test_una_serie_sin_hilo_pide_el_guion_como_siempre(session, dirs_tmp):
    ctx = series.contexto_continuidad(
        f.episodio(session, f.serie(session), numero=1).id
    )
    assert "HACIA DÓNDE VA" not in ctx


def test_el_canon_guarda_su_version_y_el_desvio(session, dirs_tmp, fake_llm):
    serie = f.serie(session)
    f.hilo(session, serie, tramos=3)
    ep = f.episodio(session, serie, numero=1)
    guiones_repo.crear(session, ep.id, GUION)
    session.commit()
    fake_llm.responder(ResumenEpisodioLLM, ResumenEpisodioLLM(
        resumen="Alicia encuentra la llave y decide no decir nada a nadie.",
        tramo_desvio="el tramo pedía que se lo contara y en el guion se lo calla",
    ))

    salida = series.generar_resumen_episodio(ep.id)

    session.refresh(ep)
    assert ep.resumen_version == 1
    assert "se lo calla" in ep.tramo_desvio
    assert "se salió de su tramo" in salida
    # El tramo entra en la petición: es contra lo que se compara.
    assert "Lo que tenía que pasar: pasa la cosa 1" in fake_llm.llamadas[-1]["user"]


def test_sin_tramo_no_hay_desvio_que_anotar(session, dirs_tmp, fake_llm):
    """Aunque el LLM se empeñe: no se le dio ningún plan contra el que comparar."""
    ep = f.episodio(session, f.serie(session), numero=1)
    guiones_repo.crear(session, ep.id, GUION)
    session.commit()
    fake_llm.responder(ResumenEpisodioLLM, ResumenEpisodioLLM(
        resumen="Alicia encuentra la llave y decide no decir nada a nadie.",
        tramo_desvio="me lo invento",
    ))

    series.generar_resumen_episodio(ep.id)

    session.refresh(ep)
    assert ep.tramo_desvio == ""


def test_lo_que_viene_detras_entra_en_corto(session, dirs_tmp, fake_llm):
    """Vetar un capítulo futuro no es contarlo: en el prompt del episodio 1 de
    seis caben cinco tramos, y escritos largos metían cinco capítulos enteros
    en el guion de uno (y cuanto más detalle, más tienta adelantarlo)."""
    serie = f.serie(session)
    parrafo = ("Marta deja el móvil grabando. " * 12).strip()
    sin_punto = "Marta " + "deja el móvil grabando y se va a la calle " * 8
    hilos_repo.crear(session, serie.id, {"tramos": [
        {"titulo": "El paquete", "pasa": "recibe el paquete", "cambia": "ya no está segura"},
        {"titulo": "La trampa", "pasa": parrafo, "cambia": "él ha entrado"},
        {"titulo": "El bloqueo", "pasa": sin_punto, "cambia": "la ley no llega"},
    ]})
    session.commit()

    ctx = series.contexto_continuidad(f.episodio(session, serie, numero=1).id)

    vetos = [x for x in ctx.splitlines() if x.startswith("- EP ")]
    # De un párrafo basta su primera frase.
    assert vetos[0] == "- EP 2 · La trampa: Marta deja el móvil grabando"
    # Y una frase sola que no acaba nunca se corta por una palabra entera.
    assert vetos[1].startswith("- EP 3 · El bloqueo: Marta deja el móvil")
    assert len(vetos[1]) < 220 and vetos[1].endswith("…")
    # El tramo propio sí va entero: es lo que tiene que hacer hoy.
    assert "Lo que pasa en este episodio: recibe el paquete" in ctx


# --- el reparto que sale del hilo -------------------------------------------

def test_el_hilo_ficha_a_los_protagonistas_en_la_serie(session, dirs_tmp, fake_llm):
    """El reparto de una serie no es de un capítulo: se ficha una vez, antes del
    primero, para poder fijarle cara y voz y que vuelvan en todos."""
    from backend.repositories import reparto as reparto_repo

    serie = f.serie(session, premisa="Alicia hereda una casa habitada.")
    _hilo_llm(fake_llm)

    log = series.generar_hilo(serie.id)

    assert "1 fichados (ALICIA)" in log
    session.expire_all()
    fichados = reparto_repo.listar(session)
    assert [(m.clave, m.nombre, m.ficha) for m in fichados] == [
        ("ALICIA", "Alicia", FICHA)
    ]
    # Y entra en el reparto fijo, que es lo que lo lleva a cada episodio.
    assert [m.reparto_slug for m in series_repo.miembros(session, serie.id)] == [
        "alicia"
    ]
    # El hilo no se queda una copia: el reparto vive en el reparto.
    assert "reparto" not in hilos_repo.contenido(session, serie.id)


def test_replanificar_no_vuelve_a_fichar_y_le_da_el_reparto_al_llm(
    session, dirs_tmp, fake_llm
):
    from backend.repositories import reparto as reparto_repo

    serie = f.serie(session, premisa="Alicia hereda una casa habitada.")
    _hilo_llm(fake_llm)
    series.generar_hilo(serie.id)
    session.expire_all()

    series.generar_hilo(serie.id)

    session.expire_all()
    # Ni un segundo Alicia en el reparto propio ni en la serie.
    assert len(reparto_repo.listar(session)) == 1
    assert len(series_repo.miembros(session, serie.id)) == 1
    # Y el LLM recibe quién es, para escribir los tramos con ella.
    user = fake_llm.llamadas[-1]["user"]
    assert "REPARTO FIJO DE LA SERIE" in user
    assert "{ALICIA} Alicia: a tired woman" in user
