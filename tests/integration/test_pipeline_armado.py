"""Armado final del video, con ffmpeg real sobre clips y audio de 1 s."""
import shutil
import subprocess

import pytest
import soundfile as sf

from backend import procesos
from backend.repositories import escenas as escenas_repo
from backend.repositories import proyectos as proyectos_repo
from backend.services.pipeline import _ffmpeg, _subtitulos_render as subs, armado, armado_estatico
from tests import factories as f

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg"),
    pytest.mark.skipif(subs.buscar_fuente("Arial Bold") is None, reason="sin fuente para los subtítulos"),
]

SRT = (
    "1\n00:00:00,000 --> 00:00:00,500\nHola mundo\n\n"
    "2\n00:00:00,500 --> 00:00:01,000\nAdiós\n"
)


@pytest.fixture(autouse=True)
def encoder_software(monkeypatch):
    """libx264 en vez de VideoToolbox: no depende del hardware y es determinista."""
    monkeypatch.setattr(_ffmpeg, "VIDEO_ENCODER", "software")
    monkeypatch.setattr(_ffmpeg, "VIDEO_CRF", 35)


@pytest.fixture
def proy(session, dirs_tmp):
    p = f.proyecto(session)
    escenas_repo.reemplazar_todas(session, p.id, [
        {"orden": o, "t_inicio": o * 0.5, "t_fin": o * 0.5 + 0.5, "texto": "t", "prompt": "p"}
        for o in (0, 1)])
    session.commit()
    return p.id


@pytest.fixture
def base(dirs_tmp):
    b = dirs_tmp["proyectos"] / "demo"
    b.mkdir(parents=True, exist_ok=True)
    return b


def _voz(base, segundos=1.0, srt=SRT):
    sf.write(base / "voz.wav", [0.0] * int(24000 * segundos), 24000)
    (base / "subtitulos.srt").write_text(srt)


def _clips(base, ordenes=(0, 1)):
    (base / "clips").mkdir(exist_ok=True)
    for o in ordenes:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
             f"color=c={'red' if o % 2 == 0 else 'blue'}:s=1080x1920:d=0.5:r=30",
             "-pix_fmt", "yuv420p", str(base / "clips" / f"{o:02d}.mp4")], check=True)


def _imagenes(base, ordenes=(0, 1)):
    from PIL import Image

    (base / "imagenes").mkdir(exist_ok=True)
    for o in ordenes:
        Image.new("RGB", (270, 480), (200, 30 * o, 30)).save(base / "imagenes" / f"{o:02d}.png")


def _sonda(video):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
         "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True)
    return {linea.split(",")[0]: linea.split(",")[1:] for linea in r.stdout.split() if linea}


# --- subtítulos -------------------------------------------------------------

def test_srt_a_bloques_lee_tiempos_y_une_lineas(tmp_path):
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:01,500 --> 00:01:02,250\nlinea uno\nlinea dos\n\n2\n01:00:00,000 --> 01:00:01,000\notra\n")
    assert subs.srt_a_bloques(srt) == [
        {"start": 1.5, "end": 62.25, "texto": "linea uno linea dos"},
        {"start": 3600.0, "end": 3601.0, "texto": "otra"}]


def test_srt_vacio_no_da_bloques(tmp_path):
    srt = tmp_path / "s.srt"
    srt.write_text("")
    assert subs.srt_a_bloques(srt) == []


def test_dibujar_subtitulo_pinta_en_la_franja_inferior():
    from PIL import Image

    img = Image.new("RGBA", (subs.ANCHO, subs.ALTO), (0, 0, 0, 0))
    subs.dibujar_subtitulo(img, "Hola", subs.buscar_fuente("Arial Bold"), "#FFFFFF", "#000000")
    caja = img.getbbox()
    assert caja is not None
    assert caja[1] > subs.ALTO // 2 and caja[3] <= subs.ALTO - subs.MARGEN_INFERIOR + 20
    assert caja[0] > 0 and caja[2] < subs.ANCHO  # centrado dentro del lienzo


def test_texto_largo_reduce_la_fuente_para_caber():
    from PIL import Image

    fuente = subs.buscar_fuente("Arial Bold")
    corto, largo = (Image.new("RGBA", (subs.ANCHO, subs.ALTO), (0, 0, 0, 0)) for _ in range(2))
    subs.dibujar_subtitulo(corto, "Hola amigos", fuente, "#FFF", "#000")
    subs.dibujar_subtitulo(largo, "palabra " * 4, fuente, "#FFF", "#000")
    caja = largo.getbbox()
    assert caja[2] - caja[0] <= subs.ANCHO_MAX_TEXTO + 20
    assert (caja[3] - caja[1]) < (corto.getbbox()[3] - corto.getbbox()[1]) * 1.5  # no se desborda


def test_texto_absurdamente_largo_no_revienta():
    """Más ancho que el lienzo incluso con la fuente mínima: se recorta, pero no falla."""
    from PIL import Image

    img = Image.new("RGBA", (subs.ANCHO, subs.ALTO), (0, 0, 0, 0))
    subs.dibujar_subtitulo(img, "palabra " * 30, subs.buscar_fuente("Arial Bold"), "#FFF", "#000")
    assert img.getbbox() is not None


def test_buscar_fuente_inexistente_cae_al_respaldo_o_none():
    resultado = subs.buscar_fuente("fuente que no existe jamas")
    assert resultado is None or resultado.exists()


# --- armar_video (movimiento) -----------------------------------------------

def test_armar_video_produce_un_mp4_con_video_y_audio(session, proy, base):
    _voz(base)
    _clips(base)

    log = armado.armar_video(proy)

    final = base / "final.mp4"
    info = _sonda(final)
    assert info["video"][:2] == ["1080", "1920"] and "audio" in info
    # Dura lo que los clips o la voz más la cola, lo que sea mayor.
    esperado = max(1.0, 1.0 + armado.VIDEO_COLA_FINAL_S)
    assert _ffmpeg.duracion(final) == pytest.approx(esperado, abs=0.3)
    assert "2 escenas" in log and "final.mp4" in log
    assert "versiones/" not in log
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado == "FINAL"
    assert (base / "clips_concat.txt").read_text() == "file 'clips/00.mp4'\nfile 'clips/01.mp4'\n"
    assert len(list((base / "subs").glob("*.png"))) == 2  # un PNG por subtítulo


def test_armar_video_dos_veces_archiva_el_anterior(session, proy, base):
    _voz(base)
    _clips(base)
    armado.armar_video(proy)
    log = armado.armar_video(proy)
    versiones = list((base / "versiones").glob("final_*.mp4"))
    assert len(versiones) == 1 and f"versiones/{versiones[0].name}" in log
    assert (base / "final.mp4").exists()


def test_armar_video_con_srt_sin_bloques_igualmente_monta(session, proy, base):
    _voz(base, srt="")
    _clips(base)
    armado.armar_video(proy)
    assert (base / "final.mp4").exists() and not list((base / "subs").glob("*.png"))


@pytest.mark.parametrize("falta,mensaje", [
    ("clips", r"Faltan clips de las escenas \[1\]"),
    ("voz", "Faltan voz.wav o subtitulos.srt"),
    ("srt", "Faltan voz.wav o subtitulos.srt"),
])
def test_armar_video_con_entradas_que_faltan(session, proy, base, falta, mensaje):
    _voz(base)
    _clips(base, (0, 1) if falta != "clips" else (0,))
    if falta == "voz":
        (base / "voz.wav").unlink()
    if falta == "srt":
        (base / "subtitulos.srt").unlink()
    with pytest.raises(ValueError, match=mensaje):
        armado.armar_video(proy)
    assert not (base / "final.mp4").exists()


def test_armar_video_sin_escenas_o_proyecto_inexistente(session, dirs_tmp):
    with pytest.raises(ValueError, match="no existe"):
        armado.armar_video(99)
    with pytest.raises(ValueError, match="No hay escenas"):
        armado.armar_video(f.proyecto(session).id)


def test_armar_video_sin_fuente_falla_con_mensaje_claro(session, proy, base, monkeypatch):
    _voz(base)
    _clips(base)
    monkeypatch.setattr(subs, "buscar_fuente", lambda nombre: None)
    with pytest.raises(RuntimeError, match="fuente"):
        armado.armar_video(proy)


def test_armar_video_con_clip_corrupto_falla_en_vez_de_entregar_un_video_incompleto(session, proy, base):
    """Regresión: ffmpeg sale con 0 aunque el concat no abra un clip y lo omitía en silencio."""
    _voz(base)
    _clips(base)
    (base / "clips" / "01.mp4").write_bytes(b"no es video")
    with pytest.raises(ValueError, match=r"escenas \[1\] están corruptos"):
        armado.armar_video(proy)
    assert not (base / "final.mp4").exists()
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado != "FINAL"


def test_armar_video_colgado_se_cancela(session, proy, base, monkeypatch):
    _voz(base)
    _clips(base)
    real = subprocess.run

    def montaje_colgado(cmd, **kw):
        if cmd[0] == "ffmpeg" and "concat" in cmd:   # solo el montaje; ffprobe sigue real
            assert kw["timeout"] == procesos.MONTAJE_S
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return real(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", montaje_colgado)
    with pytest.raises(procesos.ProcesoTimeout, match="montaje"):
        armado.armar_video(proy)


# --- armar_estatico ---------------------------------------------------------

def test_armar_estatico_produce_un_mp4_con_stills_y_audio(session, proy, base):
    _voz(base)
    _imagenes(base)

    log = armado_estatico.armar_estatico(proy)

    info = _sonda(base / "final.mp4")
    assert info["video"][:2] == ["1080", "1920"] and "audio" in info
    assert _ffmpeg.duracion(base / "final.mp4") == pytest.approx(1.0 + armado_estatico.VIDEO_COLA_FINAL_S, abs=0.3)
    assert "Video (estático): 2 escenas" in log
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado == "FINAL"
    # Un still por combinación (escena, subtítulo) y el concat los enlaza.
    assert len(list((base / "armado").glob("*.png"))) == 2
    assert (base / "estatico_concat.txt").read_text().count("file 'armado/") >= 3


def test_armar_estatico_reutiliza_stills_iguales(session, proy, base):
    """Un subtítulo que cruza la frontera de una escena no genera el mismo still dos veces
    si escena y texto coinciden."""
    _voz(base, srt="1\n00:00:00,000 --> 00:00:00,200\nA\n\n2\n00:00:00,300 --> 00:00:00,400\nA\n")
    _imagenes(base)
    armado_estatico.armar_estatico(proy)
    nombres = (base / "estatico_concat.txt").read_text().count("file 'armado/")
    assert len(list((base / "armado").glob("*.png"))) < nombres


def test_armar_estatico_archiva_el_final_anterior(session, proy, base):
    _voz(base)
    _imagenes(base)
    armado_estatico.armar_estatico(proy)
    log = armado_estatico.armar_estatico(proy)
    assert len(list((base / "versiones").glob("final_*.mp4"))) == 1 and "versiones/" in log


def test_armar_estatico_sin_subtitulos_usa_solo_las_imagenes(session, proy, base):
    _voz(base, srt="")
    _imagenes(base)
    armado_estatico.armar_estatico(proy)
    assert (base / "final.mp4").exists()


@pytest.mark.parametrize("falta,mensaje", [
    ("imagen", r"Faltan imágenes de las escenas \[1\]"),
    ("voz", "Faltan voz.wav o subtitulos.srt"),
    ("srt", "Faltan voz.wav o subtitulos.srt"),
])
def test_armar_estatico_con_entradas_que_faltan(session, proy, base, falta, mensaje):
    _voz(base)
    _imagenes(base, (0, 1) if falta != "imagen" else (0,))
    if falta == "voz":
        (base / "voz.wav").unlink()
    if falta == "srt":
        (base / "subtitulos.srt").unlink()
    with pytest.raises(ValueError, match=mensaje):
        armado_estatico.armar_estatico(proy)


def test_armar_estatico_sin_escenas_o_proyecto_inexistente(session, dirs_tmp):
    with pytest.raises(ValueError, match="no existe"):
        armado_estatico.armar_estatico(99)
    with pytest.raises(ValueError, match="No hay escenas"):
        armado_estatico.armar_estatico(f.proyecto(session).id)


def test_armar_estatico_colgado_se_cancela(session, proy, base, monkeypatch):
    _voz(base)
    _imagenes(base)

    def colgado(cmd, **kw):
        assert kw["timeout"] == procesos.MONTAJE_S
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(subprocess, "run", colgado)
    with pytest.raises(procesos.ProcesoTimeout, match="montaje estático"):
        armado_estatico.armar_estatico(proy)
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado != "FINAL"


# --- mezcla de la música (ducking) ------------------------------------------

def _pista(session, dirs_tmp, proyecto_id, mezclar=True, segundos=2.0, con_audio=True):
    """Una pista en la biblioteca de Música, enganchada al proyecto."""
    from backend.repositories import musica as musica_repo

    m = musica_repo.crear(session, "instrumental", "banda sonora", "tags", "[Intro]",
                          int(segundos), 90, "E minor", "4", "en")
    session.flush()
    if con_audio:
        car = dirs_tmp["musica"] / str(m.id)
        car.mkdir(parents=True, exist_ok=True)
        sf.write(car / "musica.wav", [0.1] * int(24000 * segundos), 24000)
    p = proyectos_repo.obtener(session, proyecto_id)
    p.musica_id = m.id
    p.musica_mezclar = mezclar
    session.commit()
    return m.id


def _canales_audio(video):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.mark.parametrize("armar,etiqueta", [
    (lambda pid: armado.armar_video(pid), "movimiento"),
    (lambda pid: armado_estatico.armar_estatico(pid), "estático"),
])
def test_armar_con_musica_la_mezcla_bajo_la_voz(session, proy, base, dirs_tmp, armar, etiqueta):
    _voz(base)
    _clips(base)
    _imagenes(base)
    mid = _pista(session, dirs_tmp, proy)

    log = armar(proy)

    assert f"con música ({mid})" in log
    final = base / "final.mp4"
    assert "audio" in _sonda(final)
    # El audio cubre todo el video: la cama se rellena con silencio si es más
    # corta, y la voz también.
    assert _ffmpeg.duracion(final) == pytest.approx(1.0 + armado.VIDEO_COLA_FINAL_S, abs=0.3)
    assert _canales_audio(final)


def test_sin_mezclar_el_video_no_cambia(session, proy, base, dirs_tmp):
    _voz(base)
    _clips(base)
    _pista(session, dirs_tmp, proy, mezclar=False)

    log = armado.armar_video(proy)

    assert "con música" not in log
    assert (base / "final.mp4").exists()


@pytest.mark.parametrize("caso,mensaje", [
    ("sin_pista", "no tiene pista"),
    ("sin_audio", "aún no tiene audio"),
    ("pista_borrada", "ya no existe"),
])
def test_mezcla_activada_sin_pista_lista_falla_antes_de_renderizar(
    session, proy, base, dirs_tmp, caso, mensaje
):
    """Un video en silencio pasaría desapercibido hasta publicarlo, así que se
    para antes de gastar el render."""
    from backend.repositories import musica as musica_repo

    _voz(base)
    _clips(base)
    if caso == "sin_pista":
        p = proyectos_repo.obtener(session, proy)
        p.musica_mezclar = True
        session.commit()
    else:
        mid = _pista(session, dirs_tmp, proy, con_audio=(caso == "pista_borrada"))
        if caso == "pista_borrada":
            musica_repo.borrar(session, musica_repo.obtener(session, mid))
            session.commit()

    with pytest.raises(ValueError, match=mensaje):
        armado.armar_video(proy)
    assert not (base / "final.mp4").exists()
