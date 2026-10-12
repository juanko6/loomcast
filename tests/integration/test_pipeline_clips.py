import os
import shutil
import subprocess

import pytest

from backend.repositories import escenas as escenas_repo
from backend.repositories import proyectos as proyectos_repo
from backend.services.pipeline import _ffmpeg, clips, escena_individual, i2v
from tests import factories as f

pytestmark = pytest.mark.integration


@pytest.fixture
def proy(session, dirs_tmp):
    p = f.proyecto(session)
    escenas_repo.reemplazar_todas(session, p.id, [
        {"orden": o, "t_inicio": o * 4.0, "t_fin": o * 4.0 + 4.0, "texto": "t",
         "prompt": "visual", "prompt_movimiento": "mueve"} for o in (0, 1, 2)])
    session.commit()
    return p.id


def _poner(dirs_tmp, carpeta, ordenes, ext):
    for o in ordenes:
        r = dirs_tmp["proyectos"] / "demo" / carpeta / f"{o:02d}.{ext}"
        r.parent.mkdir(parents=True, exist_ok=True)
        r.write_bytes(b"x")


@pytest.fixture
def ffmpeg_falso(monkeypatch):
    """Los clips reales cuestan segundos de ffmpeg: se sustituye la codificación."""
    hechos = []

    def kb(imagen, orden, dur, salida):
        hechos.append(("kenburns", orden, dur))
        salida.write_bytes(b"clip")

    def est(imagen, dur, salida):
        hechos.append(("estatico", imagen.parent.name, dur))
        salida.write_bytes(b"clip")

    def ia(imagen, prompt, seed, dur, salida, motor=None):
        hechos.append(("i2v", imagen.parent.name, prompt, motor))
        salida.write_bytes(b"clip")

    monkeypatch.setattr(clips, "clip_ken_burns", kb)
    monkeypatch.setattr(clips, "clip_estatico", est)
    monkeypatch.setattr(i2v, "clip_i2v", ia)
    return hechos


# --- pendientes_de_modo -----------------------------------------------------

def test_pendientes_de_modo(tmp_path):
    (tmp_path / "00.mp4").write_bytes(b"x")
    (tmp_path / "01.mp4").write_bytes(b"x")
    escenas = [
        {"orden": 0, "clip_modo": "kenburns"},   # hecho con el modo pedido: se salta
        {"orden": 1, "clip_modo": "i2v"},        # hecho con otro modo: se rehace
        {"orden": 2, "clip_modo": "kenburns"},   # sin archivo: se hace
        {"orden": 3},                             # anterior al registro del modo: se rehace
    ]
    assert [e["orden"] for e in clips.pendientes_de_modo(tmp_path, escenas, "kenburns")] == [1, 2, 3]
    assert len(clips.pendientes_de_modo(tmp_path, escenas, "kenburns", forzar=True)) == 4
    assert clips.pendientes_de_modo(tmp_path, [], "kenburns") == []


# --- generar_clips (Ken Burns) ---------------------------------------------

def test_generar_clips_uno_por_escena_y_registra_el_modo(session, proy, dirs_tmp, ffmpeg_falso):
    _poner(dirs_tmp, "upscale", [0, 1, 2], "png")
    log = clips.generar_clips(proy)
    assert log == "3 clips Ken Burns a 60fps"
    assert [h[:2] for h in ffmpeg_falso] == [("kenburns", 0), ("kenburns", 1), ("kenburns", 2)]
    assert all(h[2] == 4.0 for h in ffmpeg_falso)
    session.expire_all()
    assert {e.clip_modo for e in escenas_repo.por_proyecto(session, proy)} == {"kenburns"}
    assert proyectos_repo.obtener(session, proy).estado == "CLIPS"


def test_generar_clips_es_reanudable(session, proy, dirs_tmp, ffmpeg_falso):
    _poner(dirs_tmp, "upscale", [0, 1, 2], "png")
    clips.generar_clips(proy)
    ffmpeg_falso.clear()
    assert clips.generar_clips(proy) == "Los 3 clips Ken Burns ya estaban hechos"
    assert ffmpeg_falso == []
    clips.generar_clips(proy, forzar=True)
    assert len(ffmpeg_falso) == 3


def test_generar_clips_sin_reescalado_falla(session, proy, dirs_tmp, ffmpeg_falso):
    _poner(dirs_tmp, "upscale", [0], "png")
    with pytest.raises(ValueError, match=r"\[1, 2\]"):
        clips.generar_clips(proy)
    assert ffmpeg_falso == []


def test_generar_clips_sin_escenas_o_proyecto_inexistente(session, dirs_tmp, ffmpeg_falso):
    with pytest.raises(ValueError, match="no existe"):
        clips.generar_clips(99)
    with pytest.raises(ValueError, match="no tiene escenas"):
        clips.generar_clips(f.proyecto(session).id)


# --- generar_i2v ------------------------------------------------------------

def test_generar_i2v_usa_el_prompt_de_movimiento_y_libera_memoria(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    _poner(dirs_tmp, "imagenes", [0, 1, 2], "png")
    log = i2v.generar_i2v(proy)
    assert log.startswith("3 clips i2v")
    assert {h[2] for h in ffmpeg_falso} == {"mueve"}
    assert fake_comfy.nombres() == ["liberar_memoria"]
    session.expire_all()
    assert {e.clip_modo for e in escenas_repo.por_proyecto(session, proy)} == {"i2v"}
    assert proyectos_repo.obtener(session, proy).estado == "CLIPS"


def test_generar_i2v_cae_al_prompt_visual_si_no_hay_de_movimiento(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    escenas_repo.actualizar_prompts(session, proy, {o: {"prompt_movimiento": ""} for o in (0, 1, 2)})
    session.commit()
    _poner(dirs_tmp, "imagenes", [0, 1, 2], "png")
    i2v.generar_i2v(proy)
    assert {h[2] for h in ffmpeg_falso} == {"visual"}


def test_generar_i2v_salta_lo_hecho_y_distingue_el_modo(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    _poner(dirs_tmp, "imagenes", [0, 1, 2], "png")
    _poner(dirs_tmp, "clips", [0, 1], "mp4")
    escenas_repo.anotar_clip(session, proy, 0, "i2v", 1, motor="ltx25")
    escenas_repo.anotar_clip(session, proy, 1, "kenburns", 1)  # otro modo: se rehace
    session.commit()
    log = i2v.generar_i2v(proy)
    assert "2 clips i2v" in log and "(1 ya estaban)" in log
    assert i2v.generar_i2v(proy).startswith("3 clips i2v ya estaban")


def test_generar_i2v_rehace_lo_hecho_con_otro_motor(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    _poner(dirs_tmp, "imagenes", [0, 1, 2], "png")
    _poner(dirs_tmp, "clips", [0, 1, 2], "mp4")
    for orden in (0, 1, 2):
        escenas_repo.anotar_clip(session, proy, orden, "i2v", 1, motor="ltx25")
    session.commit()

    # Mismo motor: no hay nada que hacer.
    assert i2v.generar_i2v(proy, motor="ltx25").startswith("3 clips i2v ya estaban")
    # Otro motor: se rehacen las tres, y el log dice con cuál.
    log = i2v.generar_i2v(proy, motor="hunyuan")
    assert "3 clips i2v con HunyuanVideo 1.5" in log
    assert {h[3] for h in ffmpeg_falso if h[0] == "i2v"} == {"hunyuan"}


def test_generar_i2v_sin_motor_registrado_rehace(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    """Los clips de antes de que se registrara el motor cuentan como
    desconocidos: si no, un vídeo viejo se armaría mezclando motores."""
    _poner(dirs_tmp, "imagenes", [0, 1, 2], "png")
    _poner(dirs_tmp, "clips", [0, 1, 2], "mp4")
    for orden in (0, 1, 2):
        escenas_repo.anotar_clip(session, proy, orden, "i2v", 1)  # sin motor
    session.commit()
    assert "3 clips i2v" in i2v.generar_i2v(proy)


def test_i2v_error_libera_memoria_y_no_avanza(session, proy, dirs_tmp, fake_comfy, monkeypatch):
    _poner(dirs_tmp, "imagenes", [0, 1, 2], "png")

    def roto(*a, **k):
        raise RuntimeError("ComfyUI se cayó")

    monkeypatch.setattr(i2v, "clip_i2v", roto)
    with pytest.raises(RuntimeError, match="se cayó"):
        i2v.generar_i2v(proy)
    assert fake_comfy.nombres() == ["liberar_memoria"]
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado == "IDEA"


def test_generar_i2v_validaciones(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    with pytest.raises(ValueError, match=r"\[0, 1, 2\]"):
        i2v.generar_i2v(proy)
    with pytest.raises(ValueError, match="no existe"):
        i2v.generar_i2v(99)
    with pytest.raises(ValueError, match="no tiene escenas"):
        i2v.generar_i2v(f.proyecto(session, slug="vacio").id)


# --- regenerar_clip y mixto -------------------------------------------------

def test_regenerar_clip_respeta_el_modo_del_job_y_lo_guarda(session, proy, dirs_tmp, ffmpeg_falso):
    _poner(dirs_tmp, "imagenes", [1], "png")
    _poner(dirs_tmp, "upscale", [1], "png")
    log = escena_individual.regenerar_clip(proy, 1, "estatico")
    assert "escena 2" in log and "estatico" in log
    assert ffmpeg_falso == [("estatico", "upscale", 4.0)]  # prefiere la imagen reescalada
    session.expire_all()
    e = escenas_repo.por_proyecto(session, proy)[1]
    assert (e.modo, e.clip_modo) == ("estatico", "estatico")


def test_regenerar_clip_sin_upscale_usa_la_original(session, proy, dirs_tmp, ffmpeg_falso):
    _poner(dirs_tmp, "imagenes", [0], "png")
    escena_individual.regenerar_clip(proy, 0)  # sin modo: kenburns por defecto
    assert ffmpeg_falso[0][0] == "kenburns"


def test_regenerar_clip_i2v_usa_la_imagen_original_y_libera(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    _poner(dirs_tmp, "imagenes", [0], "png")
    _poner(dirs_tmp, "upscale", [0], "png")
    escena_individual.regenerar_clip(proy, 0, "i2v")
    assert ffmpeg_falso[0][:2] == ("i2v", "imagenes")
    assert fake_comfy.nombres() == ["liberar_memoria"]


@pytest.mark.parametrize("args,mensaje", [
    ((99, 0, ""), "no existe"), ((None, 9, ""), "escena 9"),
    ((None, 0, "raro"), "Modo desconocido")])
def test_regenerar_clip_invalido(session, proy, dirs_tmp, ffmpeg_falso, args, mensaje):
    pid = args[0] or proy
    with pytest.raises(ValueError, match=mensaje):
        escena_individual.regenerar_clip(pid, args[1], args[2])


def test_regenerar_clip_sin_imagen_falla(session, proy, dirs_tmp, ffmpeg_falso):
    with pytest.raises(ValueError, match="no tiene imagen"):
        escena_individual.regenerar_clip(proy, 0, "kenburns")
    assert ffmpeg_falso == []


def test_generar_clips_mixto_respeta_el_modo_de_cada_escena(session, proy, dirs_tmp, ffmpeg_falso, fake_comfy):
    for o in (0, 1, 2):
        _poner(dirs_tmp, "imagenes", [o], "png")
    escenas_repo.actualizar_prompts(session, proy, {})
    for e, modo in zip(escenas_repo.por_proyecto(session, proy), ("i2v", "estatico", "")):
        e.modo = modo
    session.commit()

    log = escena_individual.generar_clips_mixto(proy)

    assert log == "Clips generados: 1 estatico, 1 i2v, 1 kenburns"
    assert [h[0] for h in ffmpeg_falso] == ["i2v", "estatico", "kenburns"]
    ffmpeg_falso.clear()
    assert "ya estaban al día" in escena_individual.generar_clips_mixto(proy)  # kenburns quedó registrado
    assert ffmpeg_falso == []


# --- _ffmpeg (ffmpeg real, clips diminutos) --------------------------------

requiere_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg")


@requiere_ffmpeg
def test_duracion_de_un_clip_real(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1:r=10",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    assert _ffmpeg.duracion(clip) == pytest.approx(1.0, abs=0.2)


@requiere_ffmpeg
def test_duracion_de_archivo_inexistente_o_invalido_es_cero(tmp_path):
    assert _ffmpeg.duracion(tmp_path / "no_existe.mp4") == 0.0
    basura = tmp_path / "x.mp4"
    basura.write_bytes(b"no es video")
    assert _ffmpeg.duracion(basura) == 0.0


def test_archivar_final(tmp_path):
    assert _ffmpeg.archivar_final(tmp_path) is None
    final = tmp_path / "final.mp4"
    final.write_bytes(b"v1")
    os.utime(final, (1_700_000_000, 1_700_000_000))
    nombre = _ffmpeg.archivar_final(tmp_path)
    assert nombre.startswith("final_") and nombre.endswith(".mp4")
    assert not final.exists() and (tmp_path / "versiones" / nombre).read_bytes() == b"v1"


def test_args_video_segun_el_encoder(monkeypatch):
    monkeypatch.setattr(_ffmpeg, "VIDEO_ENCODER", "software")
    assert "libx264" in _ffmpeg.args_video() and "-crf" in _ffmpeg.args_video()
    monkeypatch.setattr(_ffmpeg, "VIDEO_ENCODER", "hardware")
    assert "h264_videotoolbox" in _ffmpeg.args_video()


@requiere_ffmpeg
def test_clip_estatico_real_produce_un_video_1080x1920(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(clips, "FPS", 5)
    monkeypatch.setattr(_ffmpeg, "VIDEO_ENCODER", "software")
    img = tmp_path / "i.png"
    Image.new("RGB", (90, 160), (10, 200, 30)).save(img)
    salida = tmp_path / "c.mp4"

    clips.clip_estatico(img, 0.6, salida)

    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(salida)],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "1080,1920"


@requiere_ffmpeg
@pytest.mark.parametrize("contenido", [None, b"no es imagen", b"\x89PNG\r\n\x1a\n truncado"])
@pytest.mark.parametrize("clip", ["estatico", "kenburns"])
def test_clip_con_imagen_ilegible_falla_rapido_en_vez_de_colgarse(tmp_path, clip, contenido):
    """Regresión: con `-loop 1` ffmpeg no terminaba si la imagen no se decodificaba."""
    img = tmp_path / "i.png"
    if contenido is not None:
        img.write_bytes(contenido)
    with pytest.raises(RuntimeError, match="no puede leer la imagen"):
        if clip == "estatico":
            clips.clip_estatico(img, 0.2, tmp_path / "c.mp4")
        else:
            clips.clip_ken_burns(img, 0, 0.2, tmp_path / "c.mp4")
    assert not (tmp_path / "c.mp4").exists()


def test_clip_que_excede_el_tiempo_se_cancela(tmp_path, monkeypatch):
    from PIL import Image

    img = tmp_path / "i.png"
    Image.new("RGB", (8, 8)).save(img)

    def colgado(cmd, **kw):
        assert kw["timeout"] == clips.TIMEOUT_CLIP_S
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(subprocess, "run", colgado)
    with pytest.raises(RuntimeError, match="no terminó"):
        clips.clip_estatico(img, 0.2, tmp_path / "c.mp4")
