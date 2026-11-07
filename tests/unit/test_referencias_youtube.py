from datetime import datetime, timezone

import pytest

from backend.services import referencias_youtube as ry

AHORA = datetime(2026, 11, 6, tzinfo=timezone.utc)


@pytest.mark.parametrize("iso,seg", [
    ("PT1H2M3S", 3723),
    ("PT45M", 2700),
    ("P1DT1H", 90000),
    ("PT0S", 0),
    ("", 0),
    (None, 0),
    ("basura", 0),
])
def test_duracion_s(iso, seg):
    assert ry.duracion_s(iso) == seg


def _video(**kw):
    base = {"id": "v", "titulo": "Smooth Jazz Cafe ☕ Relaxing Saxophone",
            "canal": "Groove Nest", "canal_id": "UC1", "publicado": "2026-01-01T00:00:00Z",
            "en_directo": False, "duracion_s": 3 * 3600, "visitas": 1000,
            "suscriptores": 100}
    return base | kw


@pytest.mark.parametrize("kw,motivo", [
    ({}, None),
    ({"en_directo": True}, "directo"),
    ({"duracion_s": 240}, "corto"),
    ({"canal": "Miles Davis - Topic"}, "canal Topic"),
    ({"titulo": "So What (Official Audio)"}, "artista real"),
    ({"titulo": "Kind of Blue — Full Album"}, "artista real"),
    ({"titulo": "Throwback ~ 90's R&B/Soul Playlist"}, "recopilatorio"),
    ({"titulo": "Back to the Groove : Classic 90s & 2000s R&B Mix"}, "recopilatorio"),
    ({"titulo": "Old School Mix | Usher, Keith Sweat, Maxwell"}, "recopilatorio"),
    ({"titulo": "R&B Mix | Artista Uno, Artista Dos, Artista Tres"}, "recopilatorio"),
    ({"titulo": "Rainy Jazz Cafe - Slow Jazz, Work, Study"}, None),
    ({"titulo": "Romantic Saxophone Jazz 2026 ✨ Smooth Lounge"}, None),
])
def test_motivo_descarte(kw, motivo):
    assert ry.motivo_descarte(_video(**kw)) == motivo


def test_aplanar_lee_los_tres_bloques():
    item = {
        "id": "abc",
        "snippet": {"title": "T", "description": "D", "channelId": "UC9",
                    "channelTitle": "C", "publishedAt": "2026-01-01T00:00:00Z",
                    "liveBroadcastContent": "none"},
        "statistics": {"viewCount": "1500", "likeCount": "20"},
        "contentDetails": {"duration": "PT2H"},
    }
    v = ry.aplanar(item, {"UC9": 300})
    assert v["visitas"] == 1500 and v["duracion_s"] == 7200
    assert v["suscriptores"] == 300 and v["tags"] == [] and not v["en_directo"]
    assert not v["declara_ia"]
    item["snippet"]["description"] = "Made with AI-assisted tools such as Suno AI"
    assert ry.aplanar(item, {})["declara_ia"]


def test_metricas_sin_suscriptores_no_divide_por_cero():
    m = ry.metricas(_video(suscriptores=0, visitas=500, publicado="2026-11-06T00:00:00Z"), AHORA)
    assert m["ratio_canal"] == 0.0
    assert m["visitas_dia"] == 500.0  # mínimo de un día


def test_puntuar_premia_al_que_gana_en_las_tres_metricas():
    viejo_grande = _video(id="a", visitas=5_000_000, suscriptores=2_000_000,
                          publicado="2020-01-01T00:00:00Z")
    nuevo_que_rompe = _video(id="b", visitas=2_000_000, suscriptores=20_000,
                             publicado="2026-09-01T00:00:00Z")
    flojo = _video(id="c", visitas=10_000, suscriptores=50_000,
                   publicado="2025-01-01T00:00:00Z")
    orden = [v["id"] for v in ry.puntuar([flojo, viejo_grande, nuevo_que_rompe], AHORA)]
    assert orden == ["b", "a", "c"]


def test_puntuar_vacio_y_uno_solo():
    assert ry.puntuar([]) == []
    assert ry.puntuar([_video()], AHORA)[0]["puntuacion"] == 1.0


def test_normalizar_plantilla_ignora_orden_numeros_y_acentos():
    a = ry.normalizar_plantilla("Smooth Jazz, Saxophone, mellow café, 85 bpm 🎷")
    b = ry.normalizar_plantilla("mellow cafe, saxophone, smooth jazz, 90 BPM")
    assert a == b


def _ficha(vid, canal, visitas, prompt="", genero="jazz", instrumentos=("saxophone",)):
    return {
        "video": {"id": vid, "titulo": f"t{vid}", "canal": canal, "canal_id": canal,
                  "visitas": visitas},
        "ref": ry.ReferenciaLLM(prompt_original=prompt, genero=genero,
                                instrumentos=list(instrumentos),
                                idea_semilla="Jazz suave").model_dump(),
    }


def test_agrupar_junta_la_misma_plantilla_entre_canales_y_suma():
    fichas = [
        _ficha("1", "A", 100, prompt="smooth jazz, saxophone, 85 bpm"),
        _ficha("2", "B", 300, prompt="Saxophone, smooth jazz, 90 bpm"),
        _ficha("3", "A", 50, prompt="bossa nova, nylon guitar"),
    ]
    g = ry.agrupar(fichas)
    assert len(g) == 2
    assert g[0]["visitas"] == 400 and g[0]["videos"] == 2
    assert g[0]["canales"] == ["A", "B"]
    assert g[0]["ejemplo"]["id"] == "2"  # el de más visitas


def test_agrupar_sin_prompt_separa_por_canal():
    fichas = [_ficha("1", "A", 10), _ficha("2", "A", 20), _ficha("3", "B", 5)]
    g = ry.agrupar(fichas)
    assert [x["videos"] for x in g] == [2, 1]
