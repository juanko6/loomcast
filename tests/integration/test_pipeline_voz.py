import json
import shutil
import subprocess

import pytest
import soundfile as sf

from backend.models import Voz
from backend.repositories import guiones as guiones_repo
from backend.repositories import personajes as personajes_repo
from backend.repositories import plantillas as plantillas_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import voces as voces_repo
from backend.services.pipeline import crear_voz, voz
from tests import factories as f
from tests.fakes import FakeModeloTTS

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg")]

GUION = {"gancho": "Hola", "frases": ["mundo"], "cta": "Adiós", "voz_instruct": "voz del guion"}


@pytest.fixture
def proy(session, dirs_tmp):
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, GUION)
    session.commit()
    return p.id


def _voz_lista(session, dirs_tmp, slug="ana", estado="lista", con_ref=True):
    v = Voz(slug=slug, nombre=slug, instruct="x", estado=estado)
    session.add(v)
    session.commit()
    if con_ref:
        ref = voces_repo.ruta_ref(slug)
        ref.parent.mkdir(parents=True, exist_ok=True)
        sf.write(ref, [0.0] * 2400, 24000)
    return v


# --- generar_voz ------------------------------------------------------------

def test_generar_voz_en_modo_clon(session, proy, dirs_tmp, fake_tts):
    _voz_lista(session, dirs_tmp)
    p = proyectos_repo.obtener(session, proy)
    p.voz = "ana"
    session.commit()

    log = voz.generar_voz(proy)

    base = dirs_tmp["proyectos"] / "demo"
    assert all((base / n).exists() for n in ("voz_raw.wav", "voz.wav", "voz.mp3"))
    assert fake_tts.cargados == [voz.tts.MODELO_BASE] and fake_tts.liberados == 1
    nombres = [n for n, _ in fake_tts.llamadas]
    assert nombres == ["create_voice_clone_prompt", "generate_voice_clone"]
    assert dict(fake_tts.llamadas)["generate_voice_clone"]["text"] == "Hola mundo Adiós"
    assert dict(fake_tts.llamadas)["generate_voice_clone"]["language"] == "Spanish"
    assert "clon 'ana'" in log
    # atempo de la plantilla (1.05) acorta el audio original de 0,5 s.
    assert sf.info(base / "voz.wav").duration < sf.info(base / "voz_raw.wav").duration
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado == "VOZ"


@pytest.mark.parametrize("instruct,esperado", [
    ("  a medida ", "a medida"),   # el de la UI manda
    (None, "voz del guion"),        # luego el del guion
    ("   ", "voz del guion"),       # vacío cuenta como ausente
])
def test_generar_voz_design_prioriza_instruct(session, proy, dirs_tmp, fake_tts, instruct, esperado):
    log = voz.generar_voz(proy, modo="design", instruct=instruct)
    llamada = dict(fake_tts.llamadas)["generate_voice_design"]
    assert llamada["instruct"] == esperado and fake_tts.cargados == [voz.tts.MODELO_DESIGN]
    assert "VoiceDesign" in log and (dirs_tmp["proyectos"] / "demo" / "voz.mp3").exists()


def test_generar_voz_design_sin_instruct_del_guion_usa_el_de_la_plantilla(session, dirs_tmp, fake_tts):
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, {k: v for k, v in GUION.items() if k != "voz_instruct"})
    session.commit()
    voz.generar_voz(p.id, modo="design")
    assert dict(fake_tts.llamadas)["generate_voice_design"]["instruct"].startswith("Voz masculina")


def test_clon_sin_voz_elegida(session, proy, fake_tts):
    with pytest.raises(ValueError, match="Selecciona una voz"):
        voz.generar_voz(proy)
    assert fake_tts.cargados == []


@pytest.mark.parametrize("estado,con_ref,mensaje", [
    ("generando", True, "no está disponible"),
    ("error", True, "no está disponible"),
    ("lista", False, "Falta el clip de referencia"),
])
def test_clon_con_voz_no_utilizable(session, proy, dirs_tmp, fake_tts, estado, con_ref, mensaje):
    _voz_lista(session, dirs_tmp, estado=estado, con_ref=con_ref)
    proyectos_repo.obtener(session, proy).voz = "ana"
    session.commit()
    with pytest.raises(ValueError, match=mensaje):
        voz.generar_voz(proy)
    assert fake_tts.cargados == []


def test_clon_con_voz_borrada_del_banco(session, proy, fake_tts):
    proyectos_repo.obtener(session, proy).voz = "fantasma"
    session.commit()
    with pytest.raises(ValueError, match="no está disponible"):
        voz.generar_voz(proy)


def test_generar_voz_sin_guion_o_proyecto_inexistente(session, dirs_tmp, fake_tts):
    with pytest.raises(ValueError, match="no existe"):
        voz.generar_voz(99)
    with pytest.raises(ValueError, match="guion"):
        voz.generar_voz(f.proyecto(session).id)
    assert fake_tts.cargados == []


# --- narración por tramos ---------------------------------------------------

GUION_LINEAS = {
    "gancho": "Hola",
    "lineas": [
        {"personaje": "", "texto": "esto lo cuento yo"},
        {"personaje": "ANA", "texto": "y yo lo vi"},
        {"personaje": "", "texto": "siguió contando"},
    ],
    "cta": "Adiós",
    "voz_instruct": "voz del guion",
}


@pytest.fixture
def proy_lineas(session, dirs_tmp):
    """Proyecto con guion de líneas atribuidas, voz de proyecto y ANA en el
    reparto con voz propia: cuatro tramos y dos voces."""
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, GUION_LINEAS)
    _voz_lista(session, dirs_tmp, slug="narrador")
    _voz_lista(session, dirs_tmp, slug="ana-voz")
    f.personaje(session, p.id, clave="ANA", voz="ana-voz")
    p.voz = "narrador"
    session.commit()
    return p.id


def test_narracion_por_tramos_usa_la_voz_de_cada_personaje(
    session, proy_lineas, dirs_tmp, fake_tts
):
    log = voz.generar_voz(proy_lineas)

    # Un tramo por dueño, con los seguidos del narrador unidos: gancho +
    # narración, la línea de ANA, y el resto de narración con el cta pegado.
    textos = [
        kw["text"] for n, kw in fake_tts.llamadas if n == "generate_voice_clone"
    ]
    assert textos == ["Hola esto lo cuento yo", "y yo lo vi", "siguió contando Adiós"]
    # El modelo se carga UNA vez para los tres tramos, no uno por tramo: en esta
    # máquina cargarlo cuesta más que sintetizar un tramo corto.
    assert fake_tts.cargados == [voz.tts.MODELO_BASE] and fake_tts.liberados == 1
    # Y el prompt de clonado, uno por voz distinta (dos), no uno por tramo.
    refs = [kw["ref_text"] for n, kw in fake_tts.llamadas
            if n == "create_voice_clone_prompt"]
    assert len(refs) == 2
    assert "3 de 3 tramos" in log and "con voz propia: ANA" in log


def test_los_tramos_se_unen_con_una_pausa_entre_ellos(
    session, proy_lineas, dirs_tmp, fake_tts
):
    """Sin aire entre tramos los dos se pegan y suena a corte de edición; con él
    Whisper lee la pausa y los subtítulos cortan donde cambia quien habla."""
    voz.generar_voz(proy_lineas)

    crudo = sf.info(dirs_tmp["proyectos"] / "demo" / "voz_raw.wav").duration
    # Tres tramos de 0,5 s del doble + dos pausas.
    assert crudo == pytest.approx(3 * 0.5 + 2 * voz.PAUSA_S, abs=0.02)


def test_un_personaje_sin_voz_lo_narra_la_voz_del_proyecto(
    session, proy_lineas, dirs_tmp, fake_tts
):
    """Quedarse sin su timbre es mucho mejor que un hueco en la narración. Y al
    acabar los tres tramos en la misma voz se unen en uno: partirlos no
    cambiaría el timbre, solo cortaría la prosodia y pagaría dos llamadas más.
    Es lo que pasa la primera vez que se genera la voz de un guion con líneas,
    porque el reparto se fija en un paso posterior."""
    personajes_repo.por_proyecto(session, proy_lineas)[0].voz = ""
    session.commit()

    log = voz.generar_voz(proy_lineas)

    textos = [kw["text"] for n, kw in fake_tts.llamadas
              if n == "generate_voice_clone"]
    assert textos == ["Hola esto lo cuento yo y yo lo vi siguió contando Adiós"]
    assert "con voz propia" not in log
    # Y sin tramos no hay pausas que añadir: el audio es el de una sola pasada.
    assert sf.info(dirs_tmp["proyectos"] / "demo" / "voz_raw.wav").duration == pytest.approx(0.5, abs=0.01)


@pytest.mark.parametrize("estado,con_ref", [("generando", True), ("lista", False)])
def test_una_voz_de_personaje_a_medias_no_rompe_la_narracion(
    session, proy_lineas, dirs_tmp, fake_tts, estado, con_ref
):
    """Su voz puede estar generándose todavía o haber perdido su clip. Narrar la
    línea con la voz del proyecto es la salida: la narración se entrega."""
    v = voces_repo.por_slug(session, "ana-voz")
    v.estado = estado
    if not con_ref:
        voces_repo.ruta_ref("ana-voz").unlink()
    session.commit()

    voz.generar_voz(proy_lineas)

    refs = [kw for n, kw in fake_tts.llamadas if n == "create_voice_clone_prompt"]
    assert len(refs) == 1
    sintesis = [n for n, _ in fake_tts.llamadas if n == "generate_voice_clone"]
    assert len(sintesis) == 1                  # todo con la voz del narrador
    assert (dirs_tmp["proyectos"] / "demo" / "voz.mp3").exists()


def test_un_tramo_que_falla_no_tira_la_narracion_entera(
    session, proy_lineas, dirs_tmp, fake_tts, monkeypatch
):
    """Con el formato de líneas son muchas llamadas al modelo: perder las dos
    buenas por la mala sería el peor resultado posible."""
    original = FakeModeloTTS.generate_voice_clone

    def una_falla(self, **kw):
        if kw["text"] == "y yo lo vi":
            raise RuntimeError("se fue de memoria")
        return original(self, **kw)

    monkeypatch.setattr(FakeModeloTTS, "generate_voice_clone", una_falla)

    log = voz.generar_voz(proy_lineas)

    assert "2 de 3 tramos" in log
    assert "tramo 2 (ANA)" in log and "se fue de memoria" in log
    crudo = sf.info(dirs_tmp["proyectos"] / "demo" / "voz_raw.wav").duration
    assert crudo == pytest.approx(2 * 0.5 + voz.PAUSA_S, abs=0.02)


def test_si_fallan_todos_los_tramos_la_etapa_falla(
    session, proy_lineas, dirs_tmp, fake_tts, monkeypatch
):
    """Entregar un voz.wav vacío dejaría pasar el fallo a los subtítulos y al
    montaje, que lo darían por bueno."""
    def siempre_falla(self, **kw):
        raise RuntimeError("sin memoria")

    monkeypatch.setattr(FakeModeloTTS, "generate_voice_clone", siempre_falla)

    with pytest.raises(ValueError, match="ningún tramo"):
        voz.generar_voz(proy_lineas)
    assert not (dirs_tmp["proyectos"] / "demo" / "voz.wav").exists()
    assert fake_tts.liberados == 1             # el modelo se soltó igual


def test_el_narrador_expresivo_y_los_personajes_cargan_un_modelo_cada_uno(
    session, proy_lineas, dirs_tmp, fake_tts
):
    """En modo "design" el narrador va con VoiceDesign y los personajes con
    clones: son dos modelos, y se cargan uno después de otro (no caben los dos
    en la memoria unificada de esta máquina)."""
    voz.generar_voz(proy_lineas, modo="design")

    assert fake_tts.cargados == [voz.tts.MODELO_DESIGN, voz.tts.MODELO_BASE]
    assert fake_tts.liberados == 2
    disenados = [kw["text"] for n, kw in fake_tts.llamadas
                 if n == "generate_voice_design"]
    clonados = [kw["text"] for n, kw in fake_tts.llamadas
                if n == "generate_voice_clone"]
    assert disenados == ["Hola esto lo cuento yo", "siguió contando Adiós"]
    assert clonados == ["y yo lo vi"]


def test_la_narracion_por_tramos_sigue_sirviendo_a_subtitulos_y_escenas(
    session, proy_lineas, dirs_tmp, fake_tts, fake_stt, fake_llm
):
    """Las dos etapas de detrás trabajan sobre el audio final, no sobre los
    tramos, así que varias voces no las descuadran: Whisper transcribe lo que de
    verdad se oye y las escenas se segmentan de esos timestamps. Lo que sí se
    comprueba aquí es que los tiempos siguen cuadrando con el wav concatenado,
    que es lo que podría romperse al dejar de ser una sola pasada."""
    from backend.repositories import escenas as escenas_repo
    from backend.repositories import metadatos as metadatos_repo
    from backend.schemas import EscenaLLM, StoryboardLLM
    from backend.services.pipeline import escenas, subtitulos

    voz.generar_voz(proy_lineas)
    base = dirs_tmp["proyectos"] / "demo"
    dur = sf.info(base / "voz.wav").duration
    # Whisper devolvería palabras repartidas por todo el audio concatenado.
    fake_stt.palabras = [
        {"word": f" p{i}", "start": round(i * dur / 8, 3),
         "end": round(i * dur / 8 + 0.1, 3)}
        for i in range(8)
    ]
    metadatos_repo.crear(session, proy_lineas, {"youtube": {"titulo": "T"}})
    session.commit()
    fake_llm.responder(StoryboardLLM, {"mundo": "m", "planos": [
        {"camara": "c", "accion": "a"}] * 4})
    fake_llm.responder(EscenaLLM, EscenaLLM(
        prompt="cinematic shot of a room at dusk",
        prompt_movimiento="slow push in towards the window"))

    subtitulos.generar_subtitulos(proy_lineas)
    escenas.generar_escenas(proy_lineas)

    palabras = json.loads((base / "palabras.json").read_text())
    assert palabras[-1]["end"] <= dur + 0.01
    assert (base / "subtitulos.srt").read_text().startswith("1\n00:00:00,000")
    session.expire_all()
    es = escenas_repo.por_proyecto(session, proy_lineas)
    # Los segmentos cubren el audio entero, hasta el final real del wav unido.
    assert es and es[0].t_inicio == 0.0
    assert es[-1].t_fin == pytest.approx(palabras[-1]["end"], abs=0.01)


# --- las plantillas de hoy no cambian ---------------------------------------

@pytest.mark.parametrize("plantilla", ["curiosidades", "drama", "historia"])
def test_las_plantillas_actuales_siguen_narrando_de_una_sola_pasada(
    session, dirs_tmp, fake_tts, plantilla
):
    """El formato de líneas es opt-in y hoy no lo activa ninguna plantilla: con
    las tres que hay, la etapa de voz tiene que hacer la misma llamada única al
    modelo con el texto completo que hacía antes de que esto existiera."""
    assert plantillas_repo.cargar(plantilla)["formato_guion"] in ("frases", "narracion")

    p = f.proyecto(session, slug=f"demo-{plantilla}", plantilla=plantilla)
    guiones_repo.crear(session, p.id, GUION)
    _voz_lista(session, dirs_tmp)
    p.voz = "ana"
    session.commit()

    voz.generar_voz(p.id)

    assert [n for n, _ in fake_tts.llamadas] == [
        "create_voice_clone_prompt", "generate_voice_clone"]
    assert dict(fake_tts.llamadas)["generate_voice_clone"]["text"] == "Hola mundo Adiós"
    # Y el audio es el del tramo pelado: sin pausas añadidas por delante ni por
    # detrás (el doble entrega 0,5 s).
    base = dirs_tmp["proyectos"] / f"demo-{plantilla}"
    assert sf.info(base / "voz_raw.wav").duration == pytest.approx(0.5, abs=0.01)


# --- crear_voz --------------------------------------------------------------

def _nueva(session, slug="nueva", instruct="grave y cálida"):
    v = voces_repo.crear(session, slug, slug, instruct)
    session.commit()
    return v.id


def test_crear_voz_deja_ref_y_estado_lista(session, dirs_tmp, fake_tts):
    vid = _nueva(session)
    assert crear_voz.crear_voz(vid) == "Voz 'nueva' generada"
    llamada = dict(fake_tts.llamadas)["generate_voice_design"]
    assert llamada["instruct"] == "grave y cálida" and llamada["language"] == "Spanish"
    assert sf.info(voces_repo.ruta_ref("nueva")).samplerate == 24000
    session.expire_all()
    assert voces_repo.obtener(session, vid).estado == "lista"


def test_crear_voz_si_el_modelo_falla_marca_error_y_propaga(session, dirs_tmp, fake_tts, monkeypatch):
    vid = _nueva(session)

    def roto(repo):
        raise MemoryError("sin memoria")

    monkeypatch.setattr(fake_tts, "cargar_modelo", roto)
    monkeypatch.setattr("backend.clients.tts.cargar_modelo", roto)
    with pytest.raises(MemoryError):
        crear_voz.crear_voz(vid)
    session.expire_all()
    assert voces_repo.obtener(session, vid).estado == "error"


def test_crear_voz_inexistente(engine):
    with pytest.raises(ValueError, match="no existe"):
        crear_voz.crear_voz(99)


# --- clonar_voz -------------------------------------------------------------

def _origen(dirs_tmp, slug="clon", segundos=3):
    base = dirs_tmp["voces"] / slug
    base.mkdir(parents=True, exist_ok=True)
    sf.write(base / "origen.wav", [0.1] * (24000 * segundos), 24000)


def test_clonar_voz_recorta_transcribe_y_deja_lista(session, dirs_tmp, fake_stt):
    vid = _nueva(session, "clon")
    _origen(dirs_tmp)
    fake_stt.texto = "hola, esto es una prueba"

    log = crear_voz.clonar_voz(vid, inicio=0.5, fin=1.5)

    assert sf.info(voces_repo.ruta_ref("clon")).duration == pytest.approx(1.0, abs=0.1)
    assert fake_stt.llamadas[0]["palabras"] is False
    assert "hola, esto es una prueba" in log
    session.expire_all()
    v = voces_repo.obtener(session, vid)
    assert (v.estado, v.ref_text) == ("lista", "hola, esto es una prueba")


@pytest.mark.parametrize("inicio,fin,duracion", [
    (0, None, 3.0),       # sin fin: hasta el máximo (el origen dura 3 s)
    (0, 0.1, 0.5),        # el mínimo es 0,5 s
    (-4, 2, 2.0),         # inicio negativo se trata como 0
])
def test_clonar_voz_acota_el_recorte(session, dirs_tmp, fake_stt, inicio, fin, duracion):
    vid = _nueva(session, "clon")
    _origen(dirs_tmp)
    crear_voz.clonar_voz(vid, inicio=inicio, fin=fin)
    assert sf.info(voces_repo.ruta_ref("clon")).duration == pytest.approx(duracion, abs=0.15)


def test_clonar_voz_con_transcripcion_vacia_marca_error(session, dirs_tmp, fake_stt):
    vid = _nueva(session, "clon")
    _origen(dirs_tmp)
    fake_stt.texto = ""
    with pytest.raises(ValueError, match="vacía"):
        crear_voz.clonar_voz(vid)
    session.expire_all()
    assert voces_repo.obtener(session, vid).estado == "error"


def test_clonar_voz_con_audio_corrupto_marca_error(session, dirs_tmp, fake_stt):
    vid = _nueva(session, "clon")
    base = dirs_tmp["voces"] / "clon"
    base.mkdir(parents=True)
    (base / "origen.wav").write_bytes(b"no es audio")
    with pytest.raises(subprocess.CalledProcessError):
        crear_voz.clonar_voz(vid)
    assert fake_stt.llamadas == []
    session.expire_all()
    assert voces_repo.obtener(session, vid).estado == "error"


def test_clonar_voz_sin_origen_o_inexistente(session, dirs_tmp, fake_stt):
    vid = _nueva(session, "clon")
    with pytest.raises(ValueError, match="No hay audio de origen"):
        crear_voz.clonar_voz(vid)
    with pytest.raises(ValueError, match="no existe"):
        crear_voz.clonar_voz(99)
