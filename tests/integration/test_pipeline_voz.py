import json
import shutil
import subprocess

import pytest
import soundfile as sf

from backend.models import Voz
from backend.repositories import guiones as guiones_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import voces as voces_repo
from backend.services.pipeline import crear_voz, voz
from tests import factories as f

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
