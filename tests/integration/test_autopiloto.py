"""El autopiloto y los lotes sobre la cola de verdad, con etapas de mentira.

Las etapas falsas dejan el mismo rastro que las de verdad (la fila del guion, el
voz.mp3, los PNG de las escenas, el final.mp4), porque es justo lo que el
autopiloto mira para decidir qué toca: `_que_falta` pregunta por el proyecto, no
sigue una lista fija de pasos.
"""
import json

import pytest

from backend import parada
from backend.clients import comfy
from backend.repositories import autopilotos as autopilotos_repo
from backend.repositories import escenas as escenas_repo
from backend.repositories import guiones as guiones_repo
from backend.repositories import jobs as jobs_repo
from backend.repositories import metadatos as metadatos_repo
from backend.repositories import proyectos as proyectos_repo
from backend.services import autopiloto, cancelacion
from backend.services import jobs as jobs_service
from backend.workers import queue
from tests import factories as f

pytestmark = pytest.mark.integration


@pytest.fixture
def cola(engine, monkeypatch, dirs_tmp):
    """Cola real, sin llama-server y con etapas que dejan rastro en el tmp."""
    from backend.services import llm_runtime

    monkeypatch.setattr(llm_runtime, "liberar", lambda motivo: None)
    monkeypatch.setattr(queue, "HANDLERS", dict(queue.HANDLERS))
    monkeypatch.setattr(queue, "ESPERA_BASE_S", 0)
    monkeypatch.setattr(cancelacion.comfy, "interrumpir", lambda: None)
    _vaciar()
    yield dirs_tmp["proyectos"]
    parada.limpiar()
    _vaciar()


def _vaciar():
    while not queue._cola.empty():
        queue._cola.get_nowait()


def _etapas(base_dir, hechas=None):
    """Handlers que imitan lo que cada etapa deja hecho. `hechas` recoge el
    orden en que se ejecutaron, que es lo que casi todos los tests comprueban."""
    from backend.db import get_session

    hechas = hechas if hechas is not None else []

    def _slug(pid):
        from backend.repositories import proyectos as proyectos_repo

        with get_session() as s:
            return proyectos_repo.obtener(s, pid).slug

    def anotar(tipo):
        def handler(ref, **kw):
            hechas.append(tipo)
            carpeta = base_dir / _slug(ref)
            carpeta.mkdir(parents=True, exist_ok=True)
            with get_session() as s:
                if tipo == "generar_guion":
                    guiones_repo.crear(s, ref, {"gancho": "g", "narracion": "n"})
                elif tipo == "generar_metadatos":
                    metadatos_repo.crear(s, ref, {"youtube": {}})
                elif tipo == "generar_escenas":
                    escenas_repo.reemplazar_todas(s, ref, [
                        {"orden": 1, "t_inicio": 0.0, "t_fin": 4.0,
                         "texto": "t", "prompt": "p"},
                    ])
                s.commit()
            if tipo == "generar_musica_proyecto":
                _encargar_pista(ref)
            elif tipo == "sintetizar_musica_proyecto":
                _sintetizar_pista(ref)
            elif tipo == "generar_voz":
                (carpeta / "voz.mp3").write_bytes(b"mp3")
            elif tipo == "generar_subtitulos":
                (carpeta / "palabras.json").write_text("[]")
            elif tipo == "generar_imagenes":
                (carpeta / "imagenes").mkdir(exist_ok=True)
                (carpeta / "imagenes" / "01.png").write_bytes(b"png")
            elif tipo in ("armar_video", "armar_estatico"):
                (carpeta / "final.mp4").write_bytes(b"mp4")
            return f"{tipo} hecho"

        return handler

    for tipo in ("generar_guion", "generar_metadatos", "generar_voz",
                 "generar_subtitulos", "generar_casting", "generar_retratos",
                 "generar_escenas", "generar_imagenes", "generar_musica_proyecto",
                 "sintetizar_musica_proyecto", "generar_upscale",
                 "generar_clips", "generar_i2v", "generar_clips_mixto",
                 "armar_video", "armar_estatico"):
        queue.HANDLERS[tipo] = anotar(tipo)
    return hechas


def _encargar_pista(pid):
    """Lo que deja el brief musical: la fila de `musicas` que el proyecto apunta,
    todavía sin audio."""
    from backend.db import get_session
    from backend.repositories import musica as musica_repo
    from backend.repositories import proyectos as proyectos_repo

    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        m = musica_repo.crear(s, "instrumental", "banda sonora", "ambient",
                              "[Intro]", 30, 90, "C major", "4/4", "en")
        s.flush()
        p.musica_id = m.id
        s.commit()


def _sintetizar_pista(pid):
    """Y lo que deja la síntesis: el audio de esa pista en la carpeta de Música."""
    from backend.db import get_session
    from backend.repositories import proyectos as proyectos_repo
    from backend.services.pipeline import musica as musica_pipeline

    with get_session() as s:
        musica_id = proyectos_repo.obtener(s, pid).musica_id
    car = musica_pipeline.carpeta(musica_id)
    car.mkdir(parents=True, exist_ok=True)
    (car / "musica.flac").write_bytes(b"flac")


def _correr(tope=40):
    """Procesa la cola hasta vaciarla. El tope es para que un autopiloto que se
    reencolara sin avanzar rompa el test en vez de colgarlo."""
    vueltas = 0
    while not queue._cola.empty():
        vueltas += 1
        assert vueltas <= tope, "la cola no se vacía: ¿un autopiloto en bucle?"
        queue._procesar(queue._tomar())


def _auto(pid):
    from backend.db import get_session

    with get_session() as s:
        return autopilotos_repo.ultimo_de_proyecto(s, pid)


def _proyecto_con_voz(session, slug="demo"):
    """Un proyecto recién nacido con su voz elegida, que es lo que el autopiloto
    exige para arrancar (la narración se clona de una voz del banco)."""
    p = f.proyecto(session, slug=slug)
    _voz(session)
    p.voz = "narrador"
    session.commit()
    return p


def _voz(session):
    """La voz del banco con la que narran los proyectos de estos tests."""
    from backend.repositories import voces as voces_repo

    if voces_repo.por_slug(session, "narrador") is None:
        voces_repo.crear(session, "narrador", "Narrador", "instruct")
        session.commit()


# --- la escalera ------------------------------------------------------------

def test_sin_paradas_llega_del_guion_al_video(cola, session):
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)

    autopiloto.arrancar(p.id, "kenburns", paradas=[])
    _correr()

    assert hechas == [
        "generar_guion", "generar_metadatos", "generar_voz",
        "generar_subtitulos", "generar_casting", "generar_escenas",
        "generar_imagenes", "generar_musica_proyecto",
        "sintetizar_musica_proyecto", "generar_upscale", "generar_clips",
        "armar_video",
    ]
    assert (_auto(p.id).estado, _auto(p.id).motivo) == ("hecho", autopiloto.MOTIVO_HECHO)


def test_por_defecto_para_en_el_guion_y_lo_dice(cola, session):
    """La parada del guion está puesta de serie: es la revisión más barata de
    atender y la más cara de saltarse."""
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)

    autopiloto.arrancar(p.id, "kenburns")
    _correr()

    assert hechas == ["generar_guion"]
    a = _auto(p.id)
    assert a.estado == "esperando"
    assert a.motivo == "Esperando que revises el guion"
    assert queue._cola.empty()


def test_continuar_sigue_hasta_la_parada_de_las_escenas(cola, session):
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)
    autopiloto.arrancar(p.id, "estatico")
    _correr()
    hechas.clear()

    autopiloto.continuar(p.id)
    _correr()

    assert hechas == [
        "generar_metadatos", "generar_voz", "generar_subtitulos",
        "generar_casting", "generar_escenas",
    ]
    assert _auto(p.id).motivo == "Esperando que revises los prompts de escena"

    hechas.clear()
    autopiloto.continuar(p.id)
    _correr()

    assert hechas == [
        "generar_imagenes", "generar_musica_proyecto",
        "sintetizar_musica_proyecto", "armar_estatico",
    ]
    assert _auto(p.id).estado == "hecho"


def test_una_etapa_pedida_a_mano_no_atiende_la_revision(cola, session):
    """Esperando una revisión, el autopiloto no se mueve porque se pulse algo:
    la parada es para que una persona mire, y pulsar no es mirar."""
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)
    autopiloto.arrancar(p.id, "estatico")
    _correr()
    hechas.clear()

    queue.encolar("generar_metadatos", p.id)   # como el botón del stepper
    _correr()

    assert hechas == ["generar_metadatos"]     # y nada más tras ella
    assert _auto(p.id).estado == "esperando"


def test_arranca_donde_este_el_proyecto_y_no_rehace_lo_hecho(cola, session):
    """Un proyecto a medio hacer a mano se retoma, no se repite: el autopiloto
    pregunta qué falta en vez de seguir una lista de pasos."""
    p = _proyecto_con_voz(session)
    guiones_repo.crear(session, p.id, {"gancho": "g", "narracion": "n"})
    metadatos_repo.crear(session, p.id, {"youtube": {}})
    session.commit()
    carpeta = cola / p.slug
    carpeta.mkdir(parents=True)
    (carpeta / "voz.mp3").write_bytes(b"mp3")
    (carpeta / "palabras.json").write_text("[]")
    hechas = _etapas(cola)

    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    assert hechas == [
        "generar_casting", "generar_escenas", "generar_imagenes",
        "generar_musica_proyecto", "sintetizar_musica_proyecto",
        "armar_estatico",
    ]


def test_un_proyecto_ya_montado_se_cierra_sin_encolar_nada(cola, session):
    p = _proyecto_con_voz(session)
    (cola / p.slug).mkdir(parents=True)
    (cola / p.slug / "final.mp4").write_bytes(b"mp4")
    _etapas(cola)

    datos = autopiloto.arrancar(p.id, "estatico", paradas=[])

    assert datos["estado"] == "hecho"
    assert queue._cola.empty()


def test_una_etapa_que_no_deja_rastro_detiene_la_tirada(cola, session):
    """Si lo que falta sigue siendo lo que acaba de terminar, el autopiloto se
    detiene y lo dice. Sin este freno repetiría la etapa para siempre."""
    p = _proyecto_con_voz(session)
    _etapas(cola)
    queue.HANDLERS["generar_guion"] = lambda ref, **kw: "digo que sí pero no escribo"

    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    a = _auto(p.id)
    assert a.estado == "error" and "no puede avanzar" in a.motivo


def test_un_ciclo_de_dos_etapas_tambien_se_corta(cola, session):
    """El freno de "lo que falta es lo que acabó" solo pilla una etapa repetida.
    Un montaje que dice que terminó sin dejar el final.mp4 manda al primer job
    del modo, y ese otra vez al montaje: eso lo corta el tope de etapas."""
    p = _proyecto_con_voz(session)
    _etapas(cola)
    queue.HANDLERS["armar_video"] = lambda ref, **kw: "digo que monté y no monté"

    autopiloto.arrancar(p.id, "kenburns", paradas=[])
    _correr(tope=200)

    a = _auto(p.id)
    assert a.estado == "error" and "sin llegar al vídeo" in a.motivo
    assert a.encoladas == autopiloto.TOPE_ETAPAS


def test_se_engancha_a_la_etapa_que_ya_estaba_en_la_cola(cola, session):
    """Aprobar una idea encola su guion; lanzar el autopiloto justo después no
    puede encolar otro, o se gastaría una pasada del LLM para pisar lo mismo."""
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)
    queue.encolar("generar_guion", p.id)        # lo que hace aprobar la idea

    autopiloto.arrancar(p.id, "estatico", paradas=[])

    from backend.db import get_session

    with get_session() as s:
        assert [j.tipo for j in jobs_repo.activos(s)] == ["generar_guion"]

    _correr()

    # Y la tirada sigue sola desde esa etapa, que es el punto.
    assert hechas.count("generar_guion") == 1
    assert _auto(p.id).estado == "hecho"


def test_no_se_lanza_dos_veces_sobre_el_mismo_proyecto(cola, session):
    p = _proyecto_con_voz(session)
    _etapas(cola)
    autopiloto.arrancar(p.id, "estatico")

    with pytest.raises(autopiloto.YaEnMarcha):
        autopiloto.arrancar(p.id, "estatico")


def test_sin_voz_elegida_no_arranca(cola, session):
    """Mejor decirlo al lanzar que fallar dos minutos después en la narración."""
    p = f.proyecto(session)
    _etapas(cola)

    with pytest.raises(autopiloto.SinVoz):
        autopiloto.arrancar(p.id, "estatico")


def test_el_motor_i2v_elegido_llega_a_la_etapa(cola, session):
    p = _proyecto_con_voz(session)
    recibido = {}
    _etapas(cola)
    i2v = queue.HANDLERS["generar_i2v"]
    queue.HANDLERS["generar_i2v"] = (
        lambda ref, **kw: recibido.update(kw) or i2v(ref)
    )

    autopiloto.arrancar(p.id, "i2v", motor="ltx25", paradas=[])
    _correr()

    assert recibido == {"motor": "ltx25"}


# --- música -----------------------------------------------------------------

def test_la_musica_suena_en_el_video_que_hizo_el_autopiloto(cola, session):
    """A mano la mezcla es un interruptor aparte; en automático no hay quien lo
    pulse, y una banda sonora escrita para esta historia que no suena en su
    vídeo sería media etapa."""
    p = _proyecto_con_voz(session)
    _etapas(cola)

    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    session.expire_all()
    p = proyectos_repo.obtener(session, p.id)
    assert p.musica_id is not None
    assert p.musica_mezclar is True


def test_una_pista_elegida_a_mano_no_se_rehace(cola, session):
    """Si alguien ya le puso música de la biblioteca, el autopiloto no la toca:
    elegirla fue una decisión."""
    from backend.repositories import musica as musica_repo
    from backend.services.pipeline import musica as musica_pipeline

    p = _proyecto_con_voz(session)
    m = musica_repo.crear(session, "instrumental", "una de la biblioteca",
                          "ambient", "[Intro]", 30, 90, "C major", "4/4", "en")
    session.flush()
    p.musica_id = m.id
    session.commit()
    car = musica_pipeline.carpeta(m.id)
    car.mkdir(parents=True, exist_ok=True)
    (car / "musica.flac").write_bytes(b"flac")
    hechas = _etapas(cola)

    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    assert "generar_musica_proyecto" not in hechas
    assert hechas[-1] == "armar_estatico"


def test_sin_musica_en_config_el_video_sale_solo_con_narracion(
    cola, session, monkeypatch
):
    monkeypatch.setattr(autopiloto, "AUTOPILOTO_MUSICA", False)
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)

    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    assert "generar_musica_proyecto" not in hechas
    assert _auto(p.id).estado == "hecho"
    session.expire_all()
    assert proyectos_repo.obtener(session, p.id).musica_mezclar is False


# --- parar ------------------------------------------------------------------

def test_parar_apaga_el_autopiloto_y_no_re_encola(cola, session):
    """Lo primero que se prueba: parar tiene que parar la tirada entera, no solo
    la etapa en curso. Un autopiloto que volviera a encolar sería imparable."""
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)
    bueno = queue.HANDLERS["generar_guion"]

    def guion_y_parada(ref, **kw):
        resultado = bueno(ref, **kw)
        jobs_service.parar()          # lo que haría el botón rojo a mitad
        return resultado

    queue.HANDLERS["generar_guion"] = guion_y_parada
    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    assert hechas == ["generar_guion"]
    assert queue._cola.empty()
    a = _auto(p.id)
    assert a.estado == "parado" and a.motivo == jobs_service.MOTIVO


def test_parar_tambien_apaga_los_que_esperaban_revision(cola, session):
    """El botón dice parar. Un autopiloto esperando revisión no está generando
    nada, pero dejarlo encendido haría dudar de si la parada llegó."""
    p = _proyecto_con_voz(session)
    _etapas(cola)
    autopiloto.arrancar(p.id, "estatico")
    _correr()
    assert _auto(p.id).estado == "esperando"

    jobs_service.parar()

    assert _auto(p.id).estado == "parado"
    with pytest.raises(autopiloto.NoEstaEsperando):
        autopiloto.continuar(p.id)


def test_detener_uno_corta_sus_jobs_y_deja_el_resto(cola, session):
    p = _proyecto_con_voz(session)
    otro = _proyecto_con_voz(session, slug="otro")
    _etapas(cola)
    autopiloto.arrancar(p.id, "estatico", paradas=[])
    autopiloto.arrancar(otro.id, "estatico", paradas=[])

    r = autopiloto.detener(p.id)

    assert r == {"parado": True, "jobs_cancelados": 1}
    assert _auto(p.id).estado == "parado"
    assert _auto(otro.id).estado == "corriendo"


def test_cancelar_a_mano_la_etapa_pendiente_no_deja_el_autopiloto_colgado(cola, session):
    """Un job que se cancela antes de correr no pasa por el handler, pero su
    autopiloto tiene que enterarse o se quedaría 'corriendo' sin nada en la
    cola, o sea para siempre."""
    p = _proyecto_con_voz(session)
    _etapas(cola)
    autopiloto.arrancar(p.id, "estatico", paradas=[])
    job_id = queue._tomar()
    jobs_service.cancelar(job_id)

    queue._procesar(job_id)

    assert _auto(p.id).estado == "parado"


# --- fallos -----------------------------------------------------------------

def test_un_fallo_detiene_su_proyecto_con_el_motivo_escrito(cola, session):
    p = _proyecto_con_voz(session)
    _etapas(cola)

    def roto(ref, **kw):
        raise ValueError("El proyecto no tiene escenas")

    queue.HANDLERS["generar_guion"] = roto
    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    a = _auto(p.id)
    assert a.estado == "error"
    assert "Falló «generar_guion»" in a.motivo and "no tiene escenas" in a.motivo
    assert queue._cola.empty()


def test_un_fallo_transitorio_se_reintenta_antes_de_rendirse(cola, session):
    """Los reintentos de la cola siguen siendo los de la cola: el autopiloto no
    los duplica ni se entera de ellos hasta que el job acaba."""
    p = _proyecto_con_voz(session)
    hechas = _etapas(cola)
    bueno = queue.HANDLERS["generar_guion"]
    intentos = []

    def a_la_segunda(ref, **kw):
        intentos.append(ref)
        if len(intentos) < 2:
            raise comfy.ComfyError("ComfyUI arrancando")
        return bueno(ref, **kw)

    queue.HANDLERS["generar_guion"] = a_la_segunda
    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    assert len(intentos) == 2
    assert hechas[:2] == ["generar_guion", "generar_metadatos"]
    assert _auto(p.id).estado == "hecho"


# --- memoria ----------------------------------------------------------------

def test_las_etapas_del_autopiloto_pasan_por_la_puerta_de_la_memoria(cola, session,
                                                                     monkeypatch):
    """El encadenado automático usa la cola de siempre, así que descarga el LLM
    antes de cada etapa que no sea de texto y lo carga con `en_uso` en las que
    sí. Es la secuencia que mató al backend con Killed: 9, y el atajo sería
    encolar desde dentro de una etapa."""
    import contextlib

    from backend.services import llm_runtime

    puerta = []
    monkeypatch.setattr(llm_runtime, "liberar",
                        lambda motivo: puerta.append(("liberar", motivo)))

    @contextlib.contextmanager
    def en_uso():
        puerta.append(("en_uso",))
        yield

    monkeypatch.setattr(llm_runtime, "en_uso", en_uso)
    p = _proyecto_con_voz(session)
    _etapas(cola)

    autopiloto.arrancar(p.id, "estatico", paradas=[])
    _correr()

    # Las de texto entran por `en_uso` (que espera memoria antes de lanzar el
    # modelo) y cada etapa de GPU o de proceso externo lo descarga primero.
    # La música son dos: el brief es texto y la síntesis es ComfyUI, y por eso
    # van en jobs separados y no en uno.
    assert puerta.count(("en_uso",)) == 5   # guion, metadatos, casting, escenas, brief
    assert ("liberar", "empieza generar_voz") in puerta
    assert ("liberar", "empieza generar_imagenes") in puerta
    assert ("liberar", "empieza sintetizar_musica_proyecto") in puerta
    assert ("liberar", "empieza armar_estatico") in puerta


# --- prioridad --------------------------------------------------------------

def test_un_job_pedido_a_mano_adelanta_a_los_del_autopiloto(cola, session):
    p = _proyecto_con_voz(session)
    _etapas(cola)
    primero = queue.encolar("generar_imagenes", p.id,
                            prioridad=queue.PRIORIDAD_AUTOPILOTO)
    segundo = queue.encolar("generar_escenas", p.id,
                            prioridad=queue.PRIORIDAD_AUTOPILOTO)
    a_mano = queue.encolar("regenerar_imagen", p.id, orden=1)

    assert [queue._tomar(), queue._tomar(), queue._tomar()] == [
        a_mano, primero, segundo
    ]


def test_dentro_de_la_misma_prioridad_la_cola_sigue_siendo_fifo(cola, session):
    p = _proyecto_con_voz(session)
    _etapas(cola)
    uno = queue.encolar("generar_escenas", p.id)
    dos = queue.encolar("generar_imagenes", p.id)

    assert [queue._tomar(), queue._tomar()] == [uno, dos]


def test_la_cadena_hereda_la_prioridad_de_quien_la_abrio(cola, session):
    """Un upscale pedido a mano no debe perder el sitio al llegar a los clips, y
    una tirada del autopiloto no debe adelantarse por ir encadenada."""
    p = _proyecto_con_voz(session)
    _etapas(cola)
    queue.encolar("generar_upscale", p.id, prioridad=queue.PRIORIDAD_AUTOPILOTO)
    queue._procesar(queue._tomar())

    from backend.db import get_session

    with get_session() as s:
        siguiente = jobs_repo.pendientes(s)[-1]
    assert (siguiente.tipo, siguiente.prioridad) == (
        "generar_clips", queue.PRIORIDAD_AUTOPILOTO
    )


def test_el_orden_de_la_cola_sobrevive_a_un_reinicio(cola, session):
    """`recuperar_pendientes()` re-encola lo que quedó a medias, y la prioridad
    está en la columna del job justo para que el orden vuelva igual."""
    p = _proyecto_con_voz(session)
    _etapas(cola)
    del_autopiloto = queue.encolar("generar_escenas", p.id,
                                   prioridad=queue.PRIORIDAD_AUTOPILOTO)
    a_mano = queue.encolar("regenerar_imagen", p.id, orden=1)
    _vaciar()

    queue.recuperar_pendientes()

    assert [queue._tomar(), queue._tomar()] == [a_mano, del_autopiloto]


# --- lotes ------------------------------------------------------------------

def _tema_con_ideas(session, n=3, aprobadas=None):
    t = f.tema(session)
    ideas = [f.idea(session, t.id, titulo=f"Idea {k}") for k in range(n)]
    for i, idea in enumerate(ideas):
        idea.estado = "aprobada" if (aprobadas is None or i in aprobadas) else "propuesta"
    session.commit()
    _voz(session)
    return t, ideas


def test_el_lote_produce_de_uno_en_uno_y_en_orden(cola, session):
    """La cola es de un solo hilo a propósito (las etapas se pelean por la GPU),
    así que el lote es secuencial: el segundo proyecto no empieza hasta que el
    primero deja la línea."""
    t, _ = _tema_con_ideas(session, 2)
    hechas = _etapas(cola)

    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador", paradas=[])

    assert lote["total"] == 2 and lote["pendientes"] == 1
    primero, segundo = (x["proyecto_id"] for x in lote["proyectos"])
    assert _auto(primero).estado == "corriendo"
    assert _auto(segundo).estado == "pendiente"

    _correr(tope=80)

    assert hechas.count("armar_estatico") == 2
    assert [_auto(primero).estado, _auto(segundo).estado] == ["hecho", "hecho"]


def test_una_parada_de_revision_libera_la_linea_para_el_siguiente(cola, session):
    """Si parar a revisar no dejara pasar al siguiente, un lote con las paradas
    puestas se quedaría clavado en el primer guion."""
    t, _ = _tema_con_ideas(session, 3)
    _etapas(cola)

    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador")
    _correr(tope=80)

    estados = [_auto(x["proyecto_id"]).estado for x in lote["proyectos"]]
    assert estados == ["esperando", "esperando", "esperando"]
    assert autopiloto.ver_lote(lote["id"])["esperando"] == 3


def test_un_fallo_detiene_su_proyecto_pero_no_el_lote(cola, session):
    """Que un vídeo salga mal no puede tirar los otros nueve."""
    t, _ = _tema_con_ideas(session, 3)
    hechas = _etapas(cola)
    bueno = queue.HANDLERS["generar_guion"]
    vistos = []

    def falla_el_primero(ref, **kw):
        vistos.append(ref)
        if len(vistos) == 1:
            raise ValueError("el LLM devolvió un guion vacío")
        return bueno(ref, **kw)

    queue.HANDLERS["generar_guion"] = falla_el_primero
    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador", paradas=[])
    _correr(tope=120)

    estados = [_auto(x["proyecto_id"]).estado for x in lote["proyectos"]]
    assert estados == ["error", "hecho", "hecho"]
    assert hechas.count("armar_estatico") == 2
    resumen = autopiloto.ver_lote(lote["id"])
    assert (resumen["errores"], resumen["hechos"]) == (1, 2)


def test_parar_corta_el_lote_entero(cola, session):
    t, _ = _tema_con_ideas(session, 3)
    hechas = _etapas(cola)
    bueno = queue.HANDLERS["generar_guion"]

    def guion_y_parada(ref, **kw):
        resultado = bueno(ref, **kw)
        jobs_service.parar()
        return resultado

    queue.HANDLERS["generar_guion"] = guion_y_parada
    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador", paradas=[])
    _correr(tope=40)

    assert hechas == ["generar_guion"]          # el primero y nada más
    estados = [_auto(x["proyecto_id"]).estado for x in lote["proyectos"]]
    assert estados == ["parado", "parado", "parado"]
    assert queue._cola.empty()


def test_con_la_parada_de_ideas_solo_entran_las_aprobadas(cola, session):
    t, _ = _tema_con_ideas(session, 3, aprobadas=[0, 2])
    _etapas(cola)

    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador")

    assert lote["total"] == 2


def test_sin_la_parada_de_ideas_entran_tambien_las_propuestas(cola, session):
    """Producción sin manos de verdad: tema → vídeos, sin aprobar nada."""
    t, ideas = _tema_con_ideas(session, 3, aprobadas=[0])
    ideas[2].estado = "descartada"
    session.commit()
    _etapas(cola)

    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador", paradas=[])

    # La aprobada y la propuesta; la descartada no, porque descartarla ya fue
    # una decisión.
    assert lote["total"] == 2


def test_un_lote_sin_ideas_que_producir_no_se_lanza(cola, session):
    t, ideas = _tema_con_ideas(session, 2, aprobadas=[])
    _etapas(cola)

    with pytest.raises(autopiloto.SinIdeas):
        autopiloto.lanzar_lote(t.id, "estatico", voz="narrador")


def test_el_lote_no_encola_los_guiones_de_golpe(cola, session):
    """Crear el proyecto de una idea encola su guion; en un lote eso metería los
    diez de una vez y dejaría de ser secuencial."""
    t, _ = _tema_con_ideas(session, 4)
    _etapas(cola)

    autopiloto.lanzar_lote(t.id, "estatico", voz="narrador")

    from backend.db import get_session

    with get_session() as s:
        assert len(jobs_repo.activos(s)) == 1


def test_el_lote_cuenta_por_donde_va(cola, session):
    t, _ = _tema_con_ideas(session, 3)
    _etapas(cola)
    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador", paradas=[])

    queue._procesar(queue._tomar())             # el guion del primero

    actual = autopiloto.ver_lote(lote["id"])["actual"]
    assert actual["posicion"] == 1
    assert actual["etapa"] == "generar_metadatos"
    assert actual["titulo"] == "Idea 0"
    assert autopiloto.listar_lotes()[0]["pendientes"] == 2


def test_continuar_en_medio_de_un_lote_espera_su_turno(cola, session):
    """Dos proyectos del mismo lote no pueden producir a la vez: la línea es de
    uno, y adelantar sería meter dos modelos grandes en la misma memoria."""
    t, _ = _tema_con_ideas(session, 2)
    _etapas(cola)
    lote = autopiloto.lanzar_lote(t.id, "estatico", voz="narrador")
    primero, segundo = (x["proyecto_id"] for x in lote["proyectos"])
    queue._procesar(queue._tomar())             # guion del primero → espera
    assert _auto(segundo).estado == "corriendo"

    autopiloto.continuar(primero)

    assert _auto(primero).estado == "pendiente"
    _correr(tope=80)
    assert [_auto(primero).estado, _auto(segundo).estado] == ["esperando", "esperando"]
