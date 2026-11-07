import pytest

from backend.repositories import albumes as albumes_repo
from backend.repositories import musica as musica_repo
from backend.schemas import AlbumPlanLLM, MusicaPromptLLM
from backend.services.pipeline import album as album_pipe
from backend.services.pipeline import musica as musica_pipe

pytestmark = pytest.mark.integration

FIRMA = ("Recorded live in a small room with close microphones, warm and detailed, the "
         "ride cymbal crisp and airy on top, a wide stereo image with the sax in the centre.")


def _plan(n):
    return {
        "titulo": "Noches de neón", "genero": "noir jazz",
        "banda": ["breathy tenor saxophone", "felt piano", "upright bass", "brushed drums"],
        "firma": FIRMA, "arco": "Abre en la calle y cierra al amanecer.",
        "portada": "a wet street at night, teal and amber, grainy film, no text",
        "pistas": [
            {"titulo": f"Tema {i}", "papel": "ballad", "intencion": f"Una escena distinta número {i}",
             "lead": "sax", "forma": "AABA", "energia": i % 5 + 1,
             "bpm": 80 + i, "keyscale": "d minor", "timesig": "4"}
            for i in range(1, n + 1)
        ],
    }


GUION = (
    "[Intro - 4 bars - piano]\n[Theme A - 7 bars - sax]\n[Climb - 6 bars - sax higher]\n[Answer - 3 bars - bass]\n"
    "[Outro - 4 bars - final chord rings]"
)
BRIEF = {"tags": "A slow noir jazz ballad where the sax tells the story " * 2, "lyrics": GUION,
         "bpm": 200, "keyscale": "C major", "timesig": "3", "idioma": "en"}


def _album(session, n=3, origen=None):
    a = albumes_repo.crear(session, "jazz noir de madrugada", n, 777, origen)
    session.commit()
    return a.id


def test_planificar_crea_las_pistas_con_la_semilla_del_album(session, fake_llm):
    aid = _album(session)
    fake_llm.responder(AlbumPlanLLM, _plan(3))
    album_pipe.planificar_album(aid)
    session.expire_all()
    a = albumes_repo.obtener(session, aid)
    assert a.titulo == "Noches de neón" and a.firma == FIRMA
    assert a.banda.splitlines()[0] == "breathy tenor saxophone"
    pistas = albumes_repo.pistas(session, aid)
    assert [m.pista_n for m in pistas] == [1, 2, 3]
    assert {m.seed for m in pistas} == {777}
    assert pistas[0].keyscale == "D minor" and pistas[0].bpm == 81
    assert "Una escena distinta número 1" in pistas[0].intencion and "AABA" in pistas[0].intencion


def test_planificar_falla_si_faltan_pistas(session, fake_llm):
    aid = _album(session, n=5)
    fake_llm.responder(AlbumPlanLLM, _plan(3))
    with pytest.raises(ValueError, match="3 pistas y se pidieron 5"):
        album_pipe.planificar_album(aid)


def test_desde_una_pista_la_de_origen_es_la_primera_y_no_se_toca(session, fake_llm):
    m = musica_repo.crear(session, "instrumental", "mi jazz", "tags " * 10, GUION, 95,
                          70, "A minor", "4", "en")
    m.estado, m.seed = "generada", 4242
    session.commit()
    aid = _album(session, origen=m.id)
    fake_llm.responder(AlbumPlanLLM, _plan(3))
    album_pipe.planificar_album(aid)
    assert "FROM A TRACK" in fake_llm.llamadas[0]["user"]
    session.expire_all()
    pistas = albumes_repo.pistas(session, aid)
    assert pistas[0].id == m.id and pistas[0].estado == "generada"
    assert (pistas[0].bpm, pistas[0].duracion_s, pistas[0].tags) == (70, 95, "tags " * 10)
    assert len(pistas) == 3


def test_escribir_pega_la_firma_fija_tempo_y_saca_la_duracion_del_guion(session, fake_llm):
    aid = _album(session, n=2)
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(aid)
    fake_llm.responder(MusicaPromptLLM, BRIEF)
    album_pipe.escribir_album(aid)
    session.expire_all()
    a = albumes_repo.obtener(session, aid)
    assert a.estado == "revision"
    p1 = albumes_repo.pistas(session, aid)[0]
    assert p1.tags.endswith(FIRMA)
    # Tempo y compás los pone el plan, no el brief.
    assert (p1.bpm, p1.timesig) == (81, "4")
    # 24 compases × 4 × 60 / 81 = 71 s, más la cola.
    assert p1.duracion_s == round(24 * 4 * 60 / 81) + 4
    usuario = fake_llm.llamadas[1]["user"]
    assert "ALBUM TRACK" in usuario and "breathy tenor saxophone" in usuario
    assert "Una escena distinta número 1" in usuario


def test_un_guion_malo_se_reintenta_contando_que_fallo(session, fake_llm):
    aid = _album(session, n=2)
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(aid)
    malo = BRIEF | {"lyrics": "[Intro]\n[Vamp - 64 bars - same]\n[More]"}
    fake_llm.encadenar(MusicaPromptLLM, [malo, BRIEF, BRIEF])
    album_pipe.escribir_album(aid)
    reintento = fake_llm.llamadas[2]["user"]
    assert "rejected" in reintento and "vuelta estirada" in reintento


def test_un_guion_que_nunca_vale_falla(session, fake_llm):
    aid = _album(session, n=2)
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(aid)
    fake_llm.responder(MusicaPromptLLM, BRIEF | {"lyrics": "[Intro]"})
    with pytest.raises(ValueError, match="no dio un guion válido"):
        album_pipe.escribir_album(aid)


def test_a_comfy_le_llega_el_guion_sin_compases(session, dirs_tmp, fake_comfy, monkeypatch):
    monkeypatch.setattr(musica_pipe, "MUSICA_LUFS", 0)
    m = musica_repo.crear(session, "instrumental", "x", "tags " * 10, GUION, 30, 90, "C major", "4", "en")
    session.commit()
    musica_pipe.generar(m.id)
    lyrics = dict(fake_comfy.llamadas)["generar_musica"]["lyrics"]
    assert "bars" not in lyrics and lyrics.startswith("[Intro - piano]")


def test_portada_del_album_se_copia_a_cada_pista(session, dirs_tmp, fake_llm, fake_comfy):
    aid = _album(session, n=2)
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(aid)
    album_pipe.generar_portada_album(aid)
    assert album_pipe.ruta_portada(aid) is not None
    for m in albumes_repo.pistas(session, aid):
        assert musica_pipe.ruta_portada(m.id) is not None


def test_un_segundo_album_no_repite_nombres(session, fake_llm):
    primero = _album(session, n=2)
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(primero)
    # El LLM, con el mismo género, vuelve a proponer los mismos nombres.
    segundo = _album(session, n=2)
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(segundo)
    session.expire_all()
    usuario = fake_llm.llamadas[-1]["user"]
    assert "Do NOT reuse" in usuario
    assert "Albums: Noches de neón" in usuario and "Tema 1; Tema 2" in usuario
    # Si aun así repite, el disco se numera para distinguirlo en la lista.
    assert albumes_repo.obtener(session, segundo).titulo == "Noches de neón 2"
    # El primero no se ve a sí mismo como usado.
    assert "Do NOT reuse" not in fake_llm.llamadas[0]["user"]


def test_la_base_ritmica_no_lleva_la_melodia(session, fake_llm):
    assert album_pipe._lead_ritmico("walking double bass")
    assert album_pipe._lead_ritmico("upright bass lead")
    assert album_pipe._lead_ritmico("brushed drums")
    assert not album_pipe._lead_ritmico("tenor sax and upright bass in dialogue")
    assert not album_pipe._lead_ritmico("bass clarinet")
    assert not album_pipe._lead_ritmico("clean electric guitar")

    aid = _album(session, n=2)
    malo = _plan(2)
    malo["pistas"][1]["lead"] = "upright bass"
    bueno = _plan(2)
    fake_llm.encadenar(AlbumPlanLLM, [malo, bueno])
    album_pipe.planificar_album(aid)
    # El segundo intento sabe qué falló.
    assert "rhythm-section" in fake_llm.llamadas[-1]["user"]
    session.expire_all()
    assert "Lead: sax" in albumes_repo.pistas(session, aid)[1].intencion


def test_la_pista_de_origen_conserva_su_lead(session, fake_llm):
    origen = musica_repo.crear(session, "instrumental", "jazz", "tags " * 10, GUION, 95,
                               90, "D minor", "4", "en")
    session.commit()
    aid = _album(session, n=2, origen=origen.id)
    plan = _plan(2)
    plan["pistas"][0]["lead"] = "upright bass"
    fake_llm.responder(AlbumPlanLLM, plan)
    album_pipe.planificar_album(aid)
    assert len(fake_llm.llamadas) == 1


def test_un_titulo_de_pista_repetido_se_reintenta_y_si_no_se_numera(session, fake_llm):
    primero = _album(session, n=2)
    fake_llm.responder(AlbumPlanLLM, _plan(2))
    album_pipe.planificar_album(primero)
    segundo = _album(session, n=2)
    fake_llm.encadenar(AlbumPlanLLM, [_plan(2), _plan(2)])
    album_pipe.planificar_album(segundo)
    assert "«Tema 1» already exists" in fake_llm.llamadas[-1]["user"]
    session.expire_all()
    assert [m.titulo for m in albumes_repo.pistas(session, segundo)] == ["Tema 1 2", "Tema 2 2"]
