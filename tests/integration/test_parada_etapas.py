"""Parar de verdad las etapas que no pasan por ComfyUI ni por un proceso externo.

Las de GPU se cortan con el `/interrupt` de ComfyUI y las de ffmpeg con un
SIGTERM, pero las de texto (LLM), la transcripción y la síntesis de voz son
llamadas bloqueantes en este mismo proceso. Aquí se comprueba que la parada las
alcanza: el LLM entre trozos de la respuesta, Whisper entre segmentos, y la voz
—que no se puede partir— antes de empezar, diciéndolo cuando ya era tarde.
"""
import json
import shutil

import httpx
import pytest
import soundfile as sf

from backend import parada
from backend.repositories import guiones as guiones_repo
from backend.repositories import jobs as jobs_repo
from backend.services import jobs as jobs_service
from backend.workers import queue
from tests import factories as f

pytestmark = pytest.mark.integration

GUION = {"gancho": "Hola", "frases": ["mundo"], "cta": "Adiós", "voz_instruct": "voz"}


@pytest.fixture
def cola(engine, monkeypatch):
    """La cola de verdad, sin llama-server, sin esperas y sin hablar con ComfyUI."""
    from backend.services import cancelacion, llm_runtime

    monkeypatch.setattr(llm_runtime, "liberar", lambda motivo: None)
    monkeypatch.setattr(queue, "ESPERA_BASE_S", 0)
    monkeypatch.setattr(cancelacion.comfy, "interrumpir", lambda: None)
    while not queue._cola.empty():
        queue._cola.get_nowait()
    yield
    parada.limpiar()
    while not queue._cola.empty():
        queue._cola.get_nowait()


def _estado(job_id):
    from backend.db import get_session

    with get_session() as s:
        j = jobs_repo.obtener(s, job_id)
        return j.estado, j.log


def _proyecto_con_guion(session):
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, GUION)
    session.commit()
    return p


# --- LLM --------------------------------------------------------------------

def _sse(trozo: str) -> bytes:
    return b"data: " + json.dumps({"choices": [{"delta": {"content": trozo}}]}).encode() + b"\n\n"


def test_parar_a_mitad_de_una_etapa_de_texto_la_corta_sin_esperarla(
    cola, session, http_mock, dirs_tmp
):
    """El usuario pulsa Parar mientras el modelo escribe el guion: la etapa sale
    en el trozo siguiente, no cuando el modelo termine."""
    p = _proyecto_con_guion(session)
    escritos = []

    def cuerpo():
        yield _sse('{"gancho": "Lo que ')
        # Aquí pulsa el botón: el job está corriendo y es este.
        jobs_service.parar()
        escritos.append("sigue generando")
        yield _sse('nunca se leerá"}')

    http_mock(lambda r: httpx.Response(200, content=cuerpo(),
                                       headers={"content-type": "text/event-stream"}))
    jid = queue.encolar("generar_guion", p.id)

    queue._procesar(queue._cola.get())

    estado, log = _estado(jid)
    assert estado == "cancelado" and "generando texto" in log
    # Se cortó en el primer trozo: el segundo no llegó a pedirse.
    assert escritos == ["sigue generando"]
    assert queue._cola.empty()
    # Y el guion de antes sigue siendo el último: no se guardó uno a medias.
    session.expire_all()
    assert json.loads(guiones_repo.ultimo(session, p.id).contenido) == GUION


# --- Whisper ----------------------------------------------------------------

def test_parar_antes_de_los_subtitulos_no_deja_srt_ni_palabras(
    cola, session, dirs_tmp, fake_stt, parada_pedida
):
    from backend.services.pipeline import subtitulos

    p = _proyecto_con_guion(session)
    base = dirs_tmp["proyectos"] / p.slug
    base.mkdir(parents=True, exist_ok=True)
    sf.write(base / "voz.wav", [0.0] * 2400, 24000)

    with pytest.raises(parada.Parado, match="antes de transcribir"):
        subtitulos.generar_subtitulos(p.id)

    assert not (base / "subtitulos.srt").exists()
    assert not (base / "palabras.json").exists()
    assert fake_stt.llamadas == []


# --- síntesis de voz (no se puede cortar a mitad) ---------------------------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg")
def test_parar_antes_de_sintetizar_la_voz_no_deja_audio(
    cola, session, dirs_tmp, fake_tts, parada_pedida
):
    from backend.services.pipeline import voz

    p = _proyecto_con_guion(session)

    with pytest.raises(parada.Parado, match="antes de sintetizar la voz"):
        voz.generar_voz(p.id, modo="design")

    base = dirs_tmp["proyectos"] / p.slug
    assert not (base / "voz.wav").exists() and not (base / "voz_raw.wav").exists()
    assert fake_tts.cargados == []      # ni se carga el modelo


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg")
def test_si_la_voz_ya_estaba_sintetizandose_el_log_lo_dice_y_no_encadena(
    cola, session, dirs_tmp, fake_tts, monkeypatch
):
    """La síntesis es una sola llamada a PyTorch: no se puede partir. Lo honesto
    es terminarla (su audio vale), no encadenar los subtítulos y decir en el log
    que la parada llegó tarde, en vez de aparentar que cortó."""
    from backend.clients import tts

    p = _proyecto_con_guion(session)
    # Se parchea el módulo, no el fake: la etapa resuelve `tts.cargar_modelo`
    # ahí (es lo que hace la fixture `fake_tts` para instalar el doble).
    sintetizar = tts.cargar_modelo

    def cargar_y_parar(repo):
        jobs_service.parar()        # el botón, con la síntesis ya en marcha
        return sintetizar(repo)

    monkeypatch.setattr(tts, "cargar_modelo", cargar_y_parar)
    jid = queue.encolar("generar_voz", p.id, modo="design")

    queue._procesar(queue._cola.get())

    estado, log = _estado(jid)
    assert estado == "ok"                       # el audio está entero
    assert "no se podía cortar a mitad" in log
    assert (dirs_tmp["proyectos"] / p.slug / "voz.wav").exists()
    assert queue._cola.empty()                  # pero no encadena subtítulos
