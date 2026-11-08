import pytest
from PIL import Image

from backend.clients.comfy import ComfyError
from backend.repositories import galeria as galeria_repo
from backend.repositories import musica as musica_repo
from backend.schemas import ImagenLibrePromptLLM, MusicaPromptLLM
from backend.services.pipeline import _masterizar, imagen_libre
from backend.services.pipeline import musica as musica_pipe

pytestmark = pytest.mark.integration

TAGS = "warm lo-fi hip hop with soft piano and vinyl crackle"


@pytest.fixture
def sin_masterizar(monkeypatch):
    """El masterizado es ffmpeg sobre audio real; aquí se prueba solo la orquestación."""
    llamadas = []

    def masterizar(origen, destino):
        llamadas.append((origen, destino))
        destino.write_bytes(origen.read_bytes() + b"+master")
        return {"lufs": -17.0, "pico_dbtp": 0.1}

    monkeypatch.setattr(_masterizar, "masterizar", masterizar)
    monkeypatch.setattr(musica_pipe, "MUSICA_LUFS", -14)
    return llamadas


def _pista(session, tipo="instrumental", tags=TAGS, **extra):
    m = musica_repo.crear(session, tipo, "una idea", tags, "[Intro]", 30, 100, "A minor", "4", "en")
    for k, v in extra.items():
        setattr(m, k, v)
    session.commit()
    return m.id


# --- mejorar_prompt ---------------------------------------------------------

@pytest.mark.parametrize("tipo,idioma_llm,idioma_final", [
    ("cancion", "fr", "fr"),
    ("instrumental", "fr", "en"),   # una pista instrumental siempre queda en "en"
])
def test_mejorar_prompt_guarda_y_normaliza(session, fake_llm, tipo, idioma_llm, idioma_final):
    mid = _pista(session, tipo, tags=None)
    fake_llm.responder(MusicaPromptLLM, MusicaPromptLLM(
        tags=TAGS, lyrics="[Verse]\nla la la", bpm=99999, keyscale="eb minor",
        timesig="17", idioma=idioma_llm, portada="a cover with a record player"))

    assert musica_pipe.mejorar_prompt(mid) == "Estilo, tempo y letra sugeridos"

    assert "(Duración: 30 segundos)" in fake_llm.llamadas[0]["user"]
    session.expire_all()
    m = musica_repo.obtener(session, mid)
    assert m.tags == TAGS and m.lyrics == "[Verse]\nla la la"
    assert m.bpm != 99999 and m.keyscale == "Eb minor" and m.timesig == "4"
    assert m.idioma == idioma_final and m.portada == "a cover with a record player"


def test_mejorar_prompt_elige_el_prompt_de_sistema_segun_el_tipo(session, fake_llm):
    fake_llm.responder(MusicaPromptLLM, MusicaPromptLLM(tags=TAGS, lyrics="[Intro - piano]"))
    musica_pipe.mejorar_prompt(_pista(session, "cancion"))
    musica_pipe.mejorar_prompt(_pista(session, "instrumental"))
    cancion, instrumental = (c["system"] for c in fake_llm.llamadas)
    assert cancion != instrumental


def test_mejorar_prompt_falla_si_el_guion_llega_vacio(session, fake_llm):
    # Guardarlo vacío dejaba la pista sin estructura sin que nadie lo viera;
    # fallando, la cola reintenta.
    mid = _pista(session, "instrumental", tags=None)
    fake_llm.responder(MusicaPromptLLM, MusicaPromptLLM(tags=TAGS, lyrics="  "))
    with pytest.raises(ValueError, match="guion de secciones"):
        musica_pipe.mejorar_prompt(mid)
    session.expire_all()
    assert musica_repo.obtener(session, mid).tags is None


def test_mejorar_prompt_inexistente(engine, fake_llm):
    with pytest.raises(ValueError, match="no existe"):
        musica_pipe.mejorar_prompt(99)
    assert fake_llm.llamadas == []


# --- generar ----------------------------------------------------------------

def test_generar_pasa_el_conditioning_a_comfy_y_marca_generada(session, dirs_tmp, fake_comfy, sin_masterizar):
    mid = _pista(session, seed=42)

    log = musica_pipe.generar(mid)

    llamada = dict(fake_comfy.llamadas)["generar_musica"]
    assert (llamada["tags"], llamada["seed"], llamada["bpm"], llamada["keyscale"]) == (TAGS, 42, 100, "A minor")
    assert (llamada["duracion_s"], llamada["timesig"], llamada["idioma"]) == (30, "4", "en")
    assert fake_comfy.nombres()[-1] == "liberar_memoria"
    car = musica_pipe.carpeta(mid)
    assert (car / "musica.flac").read_bytes().endswith(b"+master") and (car / "crudo.flac").exists()
    assert "masterizada" in log
    session.expire_all()
    m = musica_repo.obtener(session, mid)
    assert (m.estado, m.seed) == ("generada", 42)
    assert musica_pipe.ruta_audio(mid) == car / "musica.flac"


def test_generar_pasa_los_trozos_del_decoder_desde_config(session, dirs_tmp, fake_comfy,
                                                         sin_masterizar, monkeypatch):
    """El tamaño de trozo y el solape no son del workflow: salen de config, para
    poder ajustarlos sin reexportar el JSON. Si se quedaran en el valor por
    defecto del nodo, el pico del decoder volvería a mandar la pista al swap."""
    monkeypatch.setattr(musica_pipe, "MUSICA_TILE_SIZE", 2048)
    monkeypatch.setattr(musica_pipe, "MUSICA_OVERLAP", 256)

    musica_pipe.generar(_pista(session, seed=42))

    llamada = dict(fake_comfy.llamadas)["generar_musica"]
    assert (llamada["tile_size"], llamada["overlap"]) == (2048, 256)


def test_generar_sin_seed_elige_uno_aleatorio_y_lo_guarda(session, dirs_tmp, fake_comfy, sin_masterizar):
    mid = _pista(session)
    musica_pipe.generar(mid)
    session.expire_all()
    assert isinstance(musica_repo.obtener(session, mid).seed, int)


def test_regenerar_limpia_la_pista_anterior(session, dirs_tmp, fake_comfy, sin_masterizar):
    mid = _pista(session)
    car = musica_pipe.carpeta(mid)
    car.mkdir(parents=True)
    (car / "musica.mp3").write_bytes(b"vieja")
    (car / "crudo.mp3").write_bytes(b"vieja")
    musica_pipe.generar(mid)
    assert not (car / "musica.mp3").exists() and not (car / "crudo.mp3").exists()
    assert musica_pipe.ruta_audio(mid).suffix == ".flac"


def test_generar_si_el_masterizado_falla_deja_la_pista_cruda(session, dirs_tmp, fake_comfy, monkeypatch):
    def roto(origen, destino):
        raise _masterizar.MasterizarError("loudnorm no midió")

    monkeypatch.setattr(_masterizar, "masterizar", roto)
    monkeypatch.setattr(musica_pipe, "MUSICA_LUFS", -14)
    mid = _pista(session)

    log = musica_pipe.generar(mid)

    assert "sin masterizar: loudnorm no midió" in log
    assert musica_pipe.ruta_audio(mid).read_bytes() == b"fake-audio"  # el audio crudo sigue en su sitio
    session.expire_all()
    assert musica_repo.obtener(session, mid).estado == "generada"


def test_generar_con_lufs_cero_no_masteriza(session, dirs_tmp, fake_comfy, monkeypatch):
    monkeypatch.setattr(musica_pipe, "MUSICA_LUFS", 0)
    mid = _pista(session)
    assert musica_pipe.generar(mid) == "Pista de música generada"
    assert not (musica_pipe.carpeta(mid) / "crudo.flac").exists()


def test_generar_sin_tags_falla(session, dirs_tmp, fake_comfy):
    mid = _pista(session, tags=None)
    with pytest.raises(ValueError, match="etiquetas"):
        musica_pipe.generar(mid)
    assert fake_comfy.llamadas == []


def test_generar_error_de_comfy_libera_memoria_y_no_marca_generada(session, dirs_tmp, fake_comfy, monkeypatch):
    def roto(*a, **k):
        raise ComfyError("sin memoria")

    monkeypatch.setattr("backend.clients.comfy.generar_musica", roto)
    mid = _pista(session)
    with pytest.raises(ComfyError):
        musica_pipe.generar(mid)
    assert fake_comfy.nombres() == ["liberar_memoria"]
    session.expire_all()
    assert musica_repo.obtener(session, mid).estado != "generada"


def test_generar_inexistente(engine, fake_comfy):
    with pytest.raises(ValueError, match="no existe"):
        musica_pipe.generar(99)


# --- portada ----------------------------------------------------------------

def test_portada_con_prompt(session, dirs_tmp, fake_comfy):
    mid = _pista(session, portada="a vinyl record on a table")
    assert musica_pipe.generar_portada(mid) == "Portada generada"
    llamada = dict(fake_comfy.llamadas)["generar_imagen"]
    assert llamada["prompt"] == "a vinyl record on a table" and llamada["width"] == llamada["height"]
    assert musica_pipe.ruta_portada(mid) is not None and fake_comfy.nombres()[-1] == "liberar_memoria"


def test_portada_sin_prompt_no_inventa_nada(session, dirs_tmp, fake_comfy):
    mid = _pista(session)
    assert "nada que generar" in musica_pipe.generar_portada(mid)
    assert fake_comfy.llamadas == [] and musica_pipe.ruta_portada(mid) is None


def test_portada_de_pista_inexistente(engine, fake_comfy):
    with pytest.raises(ValueError, match="no existe"):
        musica_pipe.generar_portada(99)


# --- galería: imagen_libre --------------------------------------------------

def _imagen(session, tipo="generar", prompt="a red fox", width=512, height=768, motor="",
            **campos):
    img = galeria_repo.crear(session, tipo, "un zorro", width, height, motor, **campos)
    img.prompt = prompt
    session.commit()
    return img.id


def _fuente(imagen_id, tam=(100, 70)):
    imagen_libre.carpeta(imagen_id).mkdir(parents=True, exist_ok=True)
    Image.new("RGB", tam).save(imagen_libre.ruta_fuente(imagen_id))


def test_mejorar_prompt_de_imagen(session, dirs_tmp, fake_llm):
    iid = _imagen(session, prompt="")
    fake_llm.responder(ImagenLibrePromptLLM, ImagenLibrePromptLLM(prompt="a detailed red fox in snow"))
    assert imagen_libre.mejorar_prompt(iid) == "Prompt mejorado"
    assert fake_llm.llamadas[0]["user"] == "un zorro"
    session.expire_all()
    assert galeria_repo.obtener(session, iid).prompt == "a detailed red fox in snow"


def test_mejorar_prompt_de_edicion_exige_la_imagen_de_origen(session, dirs_tmp, fake_llm):
    iid = _imagen(session, "editar")
    with pytest.raises(ValueError, match="imagen de origen"):
        imagen_libre.mejorar_prompt(iid)
    assert fake_llm.llamadas == []


def test_generar_previews_de_texto_a_imagen(session, dirs_tmp, fake_comfy):
    iid = _imagen(session, motor="flux2klein")
    assert imagen_libre.generar_previews(iid) == "4 previews generadas"
    llamadas = [k for n, k in fake_comfy.llamadas if n == "generar_imagen"]
    assert len(llamadas) == 4
    assert {(k["width"], k["height"], k["motor"]) for k in llamadas} == {(512, 768, "flux2klein")}
    assert len({k["seed"] for k in llamadas}) > 1 and fake_comfy.nombres()[-1] == "liberar_memoria"
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert len(__import__("json").loads(img.seeds)) == 4 and img.estado == "previews"
    assert all(imagen_libre.ruta_preview(iid, i).exists() for i in range(4))


def test_generar_previews_de_edicion_conserva_el_tamano_de_la_fuente(session, dirs_tmp, fake_comfy):
    iid = _imagen(session, "editar", motor="qwen")
    _fuente(iid, (101, 75))   # se redondea hacia abajo a múltiplo de 8
    imagen_libre.generar_previews(iid)
    llamadas = [k for n, k in fake_comfy.llamadas if n == "editar_imagen"]
    assert len(llamadas) == 4
    assert {(k["width"], k["height"]) for k in llamadas} == {(96, 72)}
    assert all(k["imagenes"] == imagen_libre.ruta_fuente(iid) for k in llamadas)


def test_generar_previews_hace_las_pedidas_y_borra_las_de_una_tirada_anterior(session, dirs_tmp, fake_comfy):
    iid = _imagen(session, n_previews=6)
    imagen_libre.generar_previews(iid)
    assert len([n for n, _ in fake_comfy.llamadas if n == "generar_imagen"]) == 6
    session.expire_all()
    galeria_repo.obtener(session, iid).n_previews = 2
    session.commit()
    assert imagen_libre.generar_previews(iid) == "2 previews generadas"
    assert sorted(p.name for p in imagen_libre.carpeta(iid).glob("preview_*")) == [
        "preview_0.png", "preview_1.png"]


def test_con_estilo_el_llm_escribe_la_escena_y_el_estilo_va_tal_cual(session, dirs_tmp, fake_llm,
                                                                     fake_comfy, estilos_tmp):
    iid = _imagen(session, prompt="", estilo="tinta", detalles="un gato, no un perro")
    # La escena se pide como texto, no como JSON (ver llm.texto).
    fake_llm.responder(str, "a cat sitting on a stool.")
    imagen_libre.mejorar_prompt(iid, y_previews=True)
    llamada = fake_llm.llamadas[0]
    assert "TITLE: un zorro" in llamada["user"] and "un gato, no un perro" in llamada["user"]
    assert "STYLE GUIDE: leave room for a title" in llamada["user"]
    # La cabecera del estilo no se le enseña al LLM: la parafrasearía.
    assert "ink linework" not in llamada["user"] and "SCENE" in llamada["system"]
    session.expire_all()
    assert galeria_repo.obtener(session, iid).prompt == "a cat sitting on a stool."

    imagen_libre.generar_previews(iid)
    prompts = {k["prompt"] for n, k in fake_comfy.llamadas if n == "generar_imagen"}
    assert prompts == {"heavy ink linework, two colors. a cat sitting on a stool. risograph grain."}


def test_libre_con_detalles_los_suma_a_la_idea(session, dirs_tmp, fake_llm):
    iid = _imagen(session, prompt="", detalles="fondo verde")
    fake_llm.responder(ImagenLibrePromptLLM, ImagenLibrePromptLLM(prompt="a fox in a green field"))
    imagen_libre.mejorar_prompt(iid)
    assert fake_llm.llamadas[0]["user"] == "un zorro\n\nDetalles: fondo verde"


def test_tamano_de_una_imagen_minuscula_tiene_suelo(tmp_path):
    Image.new("RGB", (3, 5)).save(tmp_path / "a.png")
    assert imagen_libre._tamano(tmp_path / "a.png") == (8, 8)


def test_generar_previews_sin_prompt_o_inexistente(session, dirs_tmp, fake_comfy):
    with pytest.raises(ValueError, match="no tiene prompt"):
        imagen_libre.generar_previews(_imagen(session, prompt=""))
    with pytest.raises(ValueError, match="no existe"):
        imagen_libre.generar_previews(99)
    assert fake_comfy.llamadas == []


def test_error_en_una_preview_libera_memoria_y_no_guarda_seeds(session, dirs_tmp, fake_comfy, monkeypatch):
    def roto(*a, **k):
        raise ComfyError("OOM")

    monkeypatch.setattr("backend.clients.comfy.generar_imagen", roto)
    iid = _imagen(session)
    with pytest.raises(ComfyError):
        imagen_libre.generar_previews(iid)
    assert fake_comfy.nombres() == ["liberar_memoria"]
    session.expire_all()
    assert galeria_repo.obtener(session, iid).estado == "nueva"


def test_generar_final_amplia_la_preview_elegida(session, dirs_tmp, fake_comfy):
    iid = _imagen(session)
    imagen_libre.generar_previews(iid)
    fake_comfy.llamadas.clear()

    assert imagen_libre.generar_final(iid, 2) == "Imagen final ampliada (preview 3)"

    llamada = dict(fake_comfy.llamadas)["upscale_imagen"]
    assert llamada["origen"] == imagen_libre.ruta_preview(iid, 2) and imagen_libre.ruta_final(iid).exists()
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert (img.estado, img.seed_elegido) == ("final", 2)


@pytest.mark.parametrize("indice", [-1, 99])
def test_generar_final_con_preview_inexistente(session, dirs_tmp, fake_comfy, indice):
    iid = _imagen(session)
    with pytest.raises(ValueError, match="No existe la preview"):
        imagen_libre.generar_final(iid, indice)
    assert fake_comfy.llamadas == []


def test_generar_final_de_imagen_inexistente(engine, fake_comfy):
    with pytest.raises(ValueError, match="no existe"):
        imagen_libre.generar_final(99, 0)


# --- galería: imagen animada ------------------------------------------------

import json  # noqa: E402
import subprocess  # noqa: E402

from backend.schemas import AnimadaMovimientoLLM  # noqa: E402
from backend.services.pipeline import imagen_animada  # noqa: E402


def _video(destino, cuadros, w, h, fps=24):
    """Un mp4 de verdad con `cuadros` cuadros que cambian (testsrc se mueve)."""
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"testsrc2=s={w}x{h}:r={fps}", "-frames:v", str(cuadros),
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "10", str(destino)],
        stdin=subprocess.DEVNULL, check=True,
    )


def _cuadros(video):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v",
         "-show_entries", "stream=nb_read_frames,width,height", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    s = json.loads(r.stdout)["streams"][0]
    return int(s["nb_read_frames"]), s["width"], s["height"]


def _gris(video, w, h):
    import numpy as np

    crudo = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(video), "-vf", "format=gray",
         "-f", "rawvideo", "-"], capture_output=True, check=True,
    ).stdout
    return np.frombuffer(crudo, np.uint8).reshape(-1, h, w).astype(float)


@pytest.fixture
def animada_pequena(monkeypatch):
    """Animada barata: LTX a 64 de lado largo, para que ffmpeg vaya rápido."""
    monkeypatch.setattr(imagen_animada, "ANIMADA_LADO_LARGO", 64)


@pytest.fixture
def rife_real(monkeypatch):
    """RIFE de mentira que entrega un clip de verdad con los cuadros pedidos,
    para que el cierre del bucle trabaje sobre algo que ffmpeg sabe leer."""
    class Llamadas(list):
        tam = (576, 1024)   # tamaño de la imagen; el clip sale al que pide LTX

    llamadas = Llamadas()

    def interpolar(entrada, salida, fps_origen, fps_final, frames=None):
        llamadas.append({"fps_origen": fps_origen, "fps_final": fps_final, "frames": frames})
        _video(salida, frames, *imagen_animada.tamano_generacion(*llamadas.tam), fps_final)

    monkeypatch.setattr("backend.clients.rife.interpolar", interpolar)
    return llamadas


def _animada(session, estado="final", movimiento="sways gently and comes back",
             duracion=10, width=576, height=1024):
    img = galeria_repo.crear(session, "animada", "un gato groovy", width, height, "zimage")
    img.prompt = "a groovy cat sipping a milkshake"
    img.prompt_movimiento = movimiento
    img.duracion_s = duracion
    img.estado = estado
    img.seed_elegido = 1
    session.commit()
    imagen_libre.carpeta(img.id).mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(imagen_libre.ruta_final(img.id))
    return img.id


@pytest.mark.parametrize("fps,dur,cuadros", [
    (8, 10, 81), (8, 12, 97), (8, 15, 121), (12, 10, 121), (12, 13.4, 161), (12, 15, 177)])
def test_cuadros_para_son_8n_mas_1_cerca_de_la_duracion(monkeypatch, fps, dur, cuadros):
    monkeypatch.setattr(imagen_animada, "ANIMADA_FPS_ORIGEN", fps)
    assert imagen_animada.cuadros_para(dur) == cuadros
    assert (cuadros - 1) % 8 == 0


@pytest.mark.parametrize("w,h,esperado", [
    (768, 1344, (480, 864)), (1344, 768, (864, 480)), (1024, 1024, (864, 864)),
    (576, 1024, (480, 864))])
def test_tamano_de_generacion_respeta_la_forma_en_multiplos_de_32(w, h, esperado):
    assert imagen_animada.tamano_generacion(w, h) == esperado


@pytest.mark.parametrize("w,h,escala,esperado", [
    # 16:9 y 9:16, aunque la preview no lo sea justo: los tamaños de YouTube.
    (1344, 768, "1080p", (1920, 1080)), (768, 1344, "1080p", (1080, 1920)),
    (1344, 768, "2k", (2560, 1440)), (1344, 768, "4k", (3840, 2160)),
    (576, 1024, "4k", (2160, 3840)),
    # Otras formas: el lado largo manda y el corto sale de la proporción.
    (1024, 1024, "1080p", (1920, 1920)), (1344, 896, "4k", (3840, 2560))])
def test_tamano_escalado_lo_manda_el_lado_largo(w, h, escala, esperado):
    assert imagen_animada.tamano_escala(w, h, escala) == esperado


@pytest.mark.parametrize("w,h,esperado", [
    (864, 480, (854, 480)), (480, 864, (480, 854)), (864, 864, (864, 864)),
    (864, 576, (864, 576))])
def test_el_bucle_base_sale_en_16_9_exacto(w, h, esperado):
    assert imagen_animada.tamano_salida(w, h, min(w, h)) == esperado


def test_aprobar_copia_la_preview_sin_esrgan(session, dirs_tmp, fake_comfy):
    iid = _imagen(session, "animada")
    imagen_libre.generar_previews(iid)
    fake_comfy.llamadas.clear()
    imagen_animada.aprobar(iid, 2)
    assert fake_comfy.llamadas == []
    assert imagen_libre.ruta_final(iid).read_bytes() == imagen_libre.ruta_preview(iid, 2).read_bytes()
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert (img.estado, img.seed_elegido) == ("final", 2)


def test_mejorar_prompt_de_animada_usa_su_prompt_de_sistema(session, dirs_tmp, fake_llm):
    iid = _imagen(session, "animada", prompt="")
    fake_llm.responder(ImagenLibrePromptLLM, ImagenLibrePromptLLM(prompt="a groovy fox with room around it"))
    imagen_libre.mejorar_prompt(iid)
    assert "seamless video loop" in fake_llm.llamadas[0]["system"]


def test_mejorar_movimiento_pule_y_recomienda_duracion(session, dirs_tmp, fake_llm):
    iid = _animada(session, movimiento="que se balancee y beba")
    fake_llm.responder(AnimadaMovimientoLLM, AnimadaMovimientoLLM(
        prompt="The cat sways gently, sips the shake and returns to rest", duracion_s=14))
    assert "14 s" in imagen_animada.mejorar_movimiento(iid)
    user = fake_llm.llamadas[0]["user"]
    assert "IMAGE: a groovy cat sipping a milkshake" in user and "MOTION: que se balancee y beba" in user
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert (img.prompt_movimiento, img.duracion_s, img.estado) == (
        "The cat sways gently, sips the shake and returns to rest", 14, "movimiento")


def test_mejorar_movimiento_sin_texto_no_llama_al_llm(session, dirs_tmp, fake_llm):
    with pytest.raises(ValueError, match="se mueva"):
        imagen_animada.mejorar_movimiento(_animada(session, movimiento="  "))
    assert fake_llm.llamadas == []


def test_animar_pide_8n_mas_1_interpola_y_quita_el_ultimo_cuadro(
        session, dirs_tmp, fake_comfy, rife_real, animada_pequena):
    iid = _animada(session, duracion=10)
    for e in ("2k", "4k"):   # versiones de un vídeo anterior
        imagen_animada.ruta_video(iid, e).write_bytes(b"viejo")

    resumen = imagen_animada.animar(iid)

    llamada = dict(fake_comfy.llamadas)["generar_video_loop"]
    assert (llamada["frames"], llamada["fps"]) == (81, 8)
    assert (llamada["width"], llamada["height"]) == (32, 64)   # 9:16 a 64: 32×64 (no es exacto)
    assert llamada["imagen"] == imagen_libre.ruta_final(iid)
    assert llamada["prompt"] == "sways gently and comes back"
    # RIFE: (81-1)·3+1, el último sigue siendo copia del primero…
    assert rife_real == [{"fps_origen": 8, "fps_final": 24, "frames": 241}]
    # …y se tira: 240 cuadros a 24 fps son 10 s justos.
    assert _cuadros(imagen_animada.ruta_video(iid)) == (240, 32, 64)
    assert "10.0 s" in resumen
    assert fake_comfy.nombres()[-1] == "liberar_memoria"
    assert not any(imagen_animada.ruta_video(iid, e).exists() for e in ("2k", "4k"))
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert img.estado == "animada" and img.seed_video == llamada["seed"] and img.escala is None


def test_cerrar_bucle_funde_la_cola_hacia_el_primer_cuadro(tmp_path):
    entrada, salida = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _video(entrada, 49, 64, 64)
    imagen_animada.cerrar_bucle(entrada, salida, 48, 8, 64, 64)

    orig, out = _gris(entrada, 64, 64), _gris(salida, 64, 64)
    assert len(out) == 48
    import numpy as np

    dif = lambda a, b: float(np.abs(a - b).mean())   # noqa: E731
    # La cabeza no se toca; la cola se acerca al primero cuadro a cuadro.
    assert dif(out[:40], orig[:40]) < 1.5
    hacia_el_primero = [dif(out[i], out[0]) for i in range(40, 48)]
    assert hacia_el_primero == sorted(hacia_el_primero, reverse=True)
    assert dif(out[-1], out[0]) < dif(orig[47], orig[0]) / 4


def test_animar_en_horizontal_deja_el_bucle_en_16_9_exacto(
        session, dirs_tmp, fake_comfy, rife_real, monkeypatch):
    monkeypatch.setattr(imagen_animada, "ANIMADA_LADO_LARGO", 576)
    rife_real.tam = (1344, 768)
    iid = _animada(session, width=1344, height=768)
    assert "568×320" in imagen_animada.animar(iid)
    llamada = dict(fake_comfy.llamadas)["generar_video_loop"]
    assert (llamada["width"], llamada["height"]) == (576, 320)   # lo que pide LTX (1,8)
    # Recortado al centro a 16:9 con el mismo alto.
    assert _cuadros(imagen_animada.ruta_video(iid)) == (240, 568, 320)


def test_cerrar_bucle_recorta_al_centro(tmp_path):
    entrada, salida = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _video(entrada, 25, 96, 48)
    imagen_animada.cerrar_bucle(entrada, salida, 24, 6, 96, 48, recorte=(86, 48))
    assert _cuadros(salida) == (24, 86, 48)


def test_cerrar_bucle_sin_fundido_solo_recorta(tmp_path):
    entrada, salida = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _video(entrada, 25, 64, 64)
    imagen_animada.cerrar_bucle(entrada, salida, 24, 0, 64, 64)
    assert _cuadros(salida)[0] == 24


def test_animar_sin_movimiento_o_sin_imagen_aprobada(session, dirs_tmp, fake_comfy):
    with pytest.raises(ValueError, match="movimiento"):
        imagen_animada.animar(_animada(session, movimiento=""))
    iid = _animada(session)
    imagen_libre.ruta_final(iid).unlink()
    with pytest.raises(ValueError, match="aprobada"):
        imagen_animada.animar(iid)
    assert fake_comfy.llamadas == []


def test_animar_si_comfy_falla_libera_memoria_y_no_deja_video(
        session, dirs_tmp, fake_comfy, monkeypatch):
    def roto(*a, **k):
        raise ComfyError("OOM")

    monkeypatch.setattr("backend.clients.comfy.generar_video_loop", roto)
    iid = _animada(session)
    with pytest.raises(ComfyError):
        imagen_animada.animar(iid)
    assert fake_comfy.nombres() == ["liberar_memoria"]
    assert not imagen_animada.ruta_video(iid).exists()
    session.expire_all()
    assert galeria_repo.obtener(session, iid).estado == "final"


def test_animar_con_parada_pedida_no_llama_a_comfy(session, dirs_tmp, fake_comfy, parada_pedida):
    from backend.parada import Parado

    with pytest.raises(Parado):
        imagen_animada.animar(_animada(session))
    assert "generar_video_loop" not in fake_comfy.nombres()


def test_escalar_lleva_el_bucle_al_tamano_exacto(
        session, dirs_tmp, fake_comfy, fake_escalador, monkeypatch):
    monkeypatch.setitem(imagen_animada.LADO_ESCALA, "1080p", 128)
    iid = _animada(session, estado="animada", width=1344, height=768)
    _video(imagen_animada.ruta_video(iid), 12, 34, 18)

    assert "1080p" in imagen_animada.escalar(iid, "1080p")

    assert len(fake_escalador.llamadas) == 1
    assert _cuadros(imagen_animada.ruta_video(iid, "1080p")) == (12, 128, 72)
    assert fake_comfy.nombres()[-1] == "liberar_memoria"
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert (img.estado, img.escala) == ("escalada", "1080p")


def test_escalar_sin_video_o_escala_rara(session, dirs_tmp, fake_escalador):
    iid = _animada(session)
    with pytest.raises(ValueError, match="anímalo"):
        imagen_animada.escalar(iid, "4k")
    with pytest.raises(ValueError, match="Escala"):
        imagen_animada.escalar(iid, "8k")
    assert fake_escalador.llamadas == []


def test_mejorar_una_recien_creada_la_pasa_a_mejorada(session, dirs_tmp, fake_llm):
    iid = _imagen(session, prompt=None)
    fake_llm.responder(ImagenLibrePromptLLM, ImagenLibrePromptLLM(prompt="a fox in a green field"))
    imagen_libre.mejorar_prompt(iid)
    session.expire_all()
    assert galeria_repo.obtener(session, iid).estado == "mejorada"


@pytest.mark.parametrize("tipo, estado", [
    ("generar", "previews"), ("generar", "final"),
    ("animada", "final"), ("animada", "movimiento"), ("animada", "escalada"),
])
def test_reescribir_la_escena_no_esconde_lo_que_ya_hay(session, dirs_tmp, fake_llm, tipo, estado):
    """Reescribir cambia el texto y nada más: las previews, la imagen aprobada
    y el vídeo siguen a la vista hasta que se regenera."""
    iid = _imagen(session, tipo)
    img = galeria_repo.obtener(session, iid)
    img.estado, img.seeds, img.seed_elegido = estado, "[1, 2]", 1
    session.commit()
    fake_llm.responder(ImagenLibrePromptLLM, ImagenLibrePromptLLM(prompt="a fox in a snowy field"))
    imagen_libre.mejorar_prompt(iid)
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert (img.prompt, img.estado, img.seeds, img.seed_elegido) == (
        "a fox in a snowy field", estado, "[1, 2]", 1)


def test_cada_preview_se_apunta_en_cuanto_sale(session, dirs_tmp, fake_comfy, monkeypatch):
    """La UI rellena los huecos según salen: al generar la tercera, las dos
    primeras ya están en la base, y las de la tirada anterior no."""
    iid = _imagen(session, n_previews=3)
    img = galeria_repo.obtener(session, iid)
    img.seeds, img.estado = "[7, 8, 9, 10]", "previews"
    session.commit()
    imagen_libre.carpeta(iid).mkdir(parents=True, exist_ok=True)
    for i in range(4):
        Image.new("RGB", (8, 8)).save(imagen_libre.ruta_preview(iid, i))

    vistas = []
    original = fake_comfy.generar_imagen

    def mirando(prompt, seed, destino, *a, **k):
        from backend.db import get_session
        with get_session() as s:
            vistas.append(json.loads(galeria_repo.obtener(s, iid).seeds))
        return original(prompt, seed, destino, *a, **k)

    monkeypatch.setattr(imagen_libre.comfy, "generar_imagen", mirando)
    imagen_libre.generar_previews(iid)
    semillas = [k["seed"] for n, k in fake_comfy.llamadas if n == "generar_imagen"]
    assert vistas == [[], semillas[:1], semillas[:2]]
    session.expire_all()
    assert json.loads(galeria_repo.obtener(session, iid).seeds) == semillas
    assert sorted(p.name for p in imagen_libre.carpeta(iid).glob("preview_*")) == [
        "preview_0.png", "preview_1.png", "preview_2.png"]
