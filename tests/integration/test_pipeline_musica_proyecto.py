"""La música del proyecto: brief desde la historia y pista aparte."""
import pytest
import soundfile as sf

from backend.repositories import guiones as guiones_repo
from backend.repositories import musica as musica_repo
from backend.repositories import proyectos as proyectos_repo
from backend.schemas import MusicaPromptLLM
from backend.services.pipeline import musica_proyecto
from backend.workers import queue
from tests import factories as f

pytestmark = pytest.mark.integration

BRIEF = MusicaPromptLLM(
    tags="dark hybrid orchestral with bowed double bass and a low pulse, "
         "midrange left clear for a voice on top",
    lyrics="[Intro - low swell]\n[Outro - dissolves]",
    bpm=88, keyscale="e minor", timesig="4", idioma="es",
    portada="a lamp-lit window seen from deep water, no text",
)


@pytest.fixture
def historia(session, dirs_tmp):
    """Un proyecto con guion, escenas y narración de 3 s."""
    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, {
        "gancho": "Algo se mueve en la fosa",
        "frases": ["Nadie ha bajado tan hondo.", "Y lo que grabaron no se explica."],
        "cta": "Sígueme para la parte dos",
    })
    f.escenas(session, p.id, n=2)
    session.commit()
    base = dirs_tmp["proyectos"] / p.slug
    base.mkdir(parents=True, exist_ok=True)
    sf.write(base / "voz.wav", [0.0] * (24000 * 3), 24000)
    return p.id


def test_el_brief_sale_de_la_historia_y_dura_lo_que_la_voz(
    session, historia, fake_llm, jobs_encolados
):
    fake_llm.responder(MusicaPromptLLM, BRIEF)

    log = musica_proyecto.generar_musica_proyecto(historia)

    # La petición lleva la historia, no una idea suelta.
    user = fake_llm.llamadas[0]["user"]
    assert "Algo se mueve en la fosa" in user
    assert "lo que grabaron no se explica" in user
    assert "prompt visual de la escena 1" in user
    # 3 s de voz + la cola final de imagen (1.5 s), redondeado hacia arriba.
    assert "must last exactly 5 seconds" in user
    assert "5 s" in log and "88 BPM" in log

    session.expire_all()
    p = proyectos_repo.obtener(session, historia)
    m = musica_repo.obtener(session, p.musica_id)
    assert m.tipo == "instrumental"
    assert m.duracion_s == 5 and m.bpm == 88 and m.keyscale == "E minor"
    # Lleva narración encima: nada cantado, así que el idioma del LLM se ignora.
    assert m.idioma == "en"
    assert m.estado == "nueva"
    # La pista no se queda en el brief: la síntesis va a la cola.
    assert ("generar_musica", m.id) in jobs_encolados


def test_sin_voz_todavia_cae_a_la_duracion_por_defecto(
    session, historia, dirs_tmp, fake_llm, jobs_encolados
):
    (dirs_tmp["proyectos"] / "demo" / "voz.wav").unlink()
    fake_llm.responder(MusicaPromptLLM, BRIEF)

    musica_proyecto.generar_musica_proyecto(historia)

    session.expire_all()
    p = proyectos_repo.obtener(session, historia)
    assert musica_repo.obtener(session, p.musica_id).duracion_s == 30


def test_rehacerla_reescribe_la_pista_en_vez_de_duplicarla(
    session, historia, fake_llm, jobs_encolados
):
    fake_llm.responder(MusicaPromptLLM, BRIEF)
    musica_proyecto.generar_musica_proyecto(historia)
    session.expire_all()
    primera = proyectos_repo.obtener(session, historia).musica_id
    musica_repo.marcar_generada(session, musica_repo.obtener(session, primera), 7)
    session.commit()

    fake_llm.responder(MusicaPromptLLM, BRIEF.model_copy(update={"bpm": 120}))
    musica_proyecto.generar_musica_proyecto(historia)

    session.expire_all()
    assert proyectos_repo.obtener(session, historia).musica_id == primera
    assert len(musica_repo.listar(session)) == 1
    m = musica_repo.obtener(session, primera)
    # Vuelve a "nueva" y sin seed: el audio que había era de otro brief.
    assert m.bpm == 120 and m.estado == "nueva" and m.seed is None


def test_sin_guion_no_hay_musica(session, dirs_tmp, fake_llm):
    p = f.proyecto(session)
    with pytest.raises(ValueError, match="guion"):
        musica_proyecto.generar_musica_proyecto(p.id)
    assert fake_llm.llamadas == []


def test_el_job_esta_registrado_y_pasa_por_el_llm():
    assert queue.HANDLERS["generar_musica_proyecto"] is musica_proyecto.generar_musica_proyecto
    assert "generar_musica_proyecto" in queue.JOBS_LLM
