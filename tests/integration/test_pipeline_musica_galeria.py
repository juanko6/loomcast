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

def _imagen(session, tipo="generar", prompt="a red fox", width=512, height=768, motor=""):
    img = galeria_repo.crear(session, tipo, "un zorro", width, height, motor)
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
    assert imagen_libre.generar_previews(iid) == f"{imagen_libre.N_PREVIEWS} previews generadas"
    llamadas = [k for n, k in fake_comfy.llamadas if n == "generar_imagen"]
    assert len(llamadas) == imagen_libre.N_PREVIEWS
    assert {(k["width"], k["height"], k["motor"]) for k in llamadas} == {(512, 768, "flux2klein")}
    assert len({k["seed"] for k in llamadas}) > 1 and fake_comfy.nombres()[-1] == "liberar_memoria"
    session.expire_all()
    img = galeria_repo.obtener(session, iid)
    assert len(__import__("json").loads(img.seeds)) == imagen_libre.N_PREVIEWS and img.estado == "previews"
    assert all(imagen_libre.ruta_preview(iid, i).exists() for i in range(imagen_libre.N_PREVIEWS))


def test_generar_previews_de_edicion_conserva_el_tamano_de_la_fuente(session, dirs_tmp, fake_comfy):
    iid = _imagen(session, "editar", motor="qwen")
    _fuente(iid, (101, 75))   # se redondea hacia abajo a múltiplo de 8
    imagen_libre.generar_previews(iid)
    llamadas = [k for n, k in fake_comfy.llamadas if n == "editar_imagen"]
    assert len(llamadas) == imagen_libre.N_PREVIEWS
    assert {(k["width"], k["height"]) for k in llamadas} == {(96, 72)}
    assert all(k["imagenes"] == imagen_libre.ruta_fuente(iid) for k in llamadas)


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
