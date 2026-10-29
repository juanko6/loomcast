import os

import pytest

from backend import parada
from backend.clients.comfy import ComfyError
from backend.repositories import escenas as escenas_repo
from backend.repositories import proyectos as proyectos_repo
from backend.services.pipeline import imagenes, retratos, upscale
from tests import factories as f

pytestmark = pytest.mark.integration


@pytest.fixture
def proy(session, dirs_tmp):
    p = f.proyecto(session)
    f.escenas(session, p.id, n=3)
    return p.id


def _retrato(dirs_tmp, clave="ANA"):
    ruta = dirs_tmp["proyectos"] / "demo" / "personajes" / f"{clave}.png"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"png")
    return ruta


# --- generar_imagenes -------------------------------------------------------

def test_generar_imagenes_una_por_escena_y_libera_memoria(session, proy, fake_comfy, dirs_tmp):
    log = imagenes.generar_imagenes(proy)

    assert log == "3 imágenes generadas"
    assert fake_comfy.nombres() == ["generar_imagen"] * 3 + ["liberar_memoria"]
    assert sorted(p.name for p in (dirs_tmp["proyectos"] / "demo" / "imagenes").iterdir()) == [
        "01.png", "02.png", "03.png"]
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado == "IMAGENES"
    assert all(e.imagen_s >= 0 for e in escenas_repo.por_proyecto(session, proy))


def test_generar_imagenes_con_retrato_usa_edicion_con_referencias(session, proy, fake_comfy, dirs_tmp):
    f.personaje(session, proy)
    escenas_repo.actualizar_prompts(session, proy, {1: {"personajes": "ANA"}})
    session.commit()
    retrato = _retrato(dirs_tmp)

    log = imagenes.generar_imagenes(proy)

    assert fake_comfy.nombres().count("editar_imagen") == 1
    llamada = dict(fake_comfy.llamadas)["editar_imagen"]
    assert llamada["imagenes"] == [retrato]
    assert llamada["prompt"].startswith(imagenes.PREFIJO_REFERENCIA)
    assert "1 con el reparto (2 sin personajes)" in log


def test_generar_imagenes_agrupa_por_motor_para_no_recargar(session, proy, fake_comfy, dirs_tmp):
    """Primero todas las de texto→imagen y luego todas las de edición.

    Alternando, ComfyUI suelta un stack y carga el otro en cada cambio (~19 GB
    el de personajes), y los picos acaban en swap. Agrupadas son dos cargas.
    Las imágenes salen iguales: cada una se guarda en su `orden`.
    """
    f.personaje(session, proy)
    # La primera y la última llevan reparto; la de en medio no (las escenas del
    # factory van numeradas desde 1). En el orden del guion eso serían dos
    # cambios de motor.
    escenas_repo.actualizar_prompts(session, proy, {1: {"personajes": "ANA"},
                                                   3: {"personajes": "ANA"}})
    session.commit()
    _retrato(dirs_tmp)

    imagenes.generar_imagenes(proy)

    assert fake_comfy.nombres() == ["generar_imagen", "editar_imagen",
                                    "editar_imagen", "liberar_memoria"]


def test_escena_con_personaje_sin_retrato_cae_a_texto(session, proy, fake_comfy):
    f.personaje(session, proy)
    escenas_repo.actualizar_prompts(session, proy, {1: {"personajes": "ANA"}})
    session.commit()
    imagenes.generar_imagenes(proy)
    assert "editar_imagen" not in fake_comfy.nombres()


def test_generar_imagenes_sin_escenas_falla_sin_tocar_comfy(session, dirs_tmp, fake_comfy):
    p = f.proyecto(session)
    with pytest.raises(ValueError, match="escenas"):
        imagenes.generar_imagenes(p.id)
    assert fake_comfy.llamadas == []


def test_generar_imagenes_proyecto_inexistente(engine, fake_comfy):
    with pytest.raises(ValueError, match="no existe"):
        imagenes.generar_imagenes(99)


def test_error_de_comfy_propaga_pero_libera_memoria_y_no_avanza(session, proy, fake_comfy, monkeypatch):
    def roto(*a, **kw):
        raise ComfyError("OOM")

    monkeypatch.setattr(fake_comfy, "generar_imagen", roto)
    monkeypatch.setattr("backend.clients.comfy.generar_imagen", roto)

    with pytest.raises(ComfyError, match="OOM"):
        imagenes.generar_imagenes(proy)

    assert fake_comfy.nombres() == ["liberar_memoria"]
    session.expire_all()
    assert proyectos_repo.obtener(session, proy).estado == "IDEA"


# --- regenerar_imagen -------------------------------------------------------

def test_regenerar_con_nuevo_seed_cambia_el_seed_guardado(session, proy, fake_comfy):
    antes = escenas_repo.por_proyecto(session, proy)[1].seed
    log = imagenes.regenerar_imagen(proy, 2, nuevo_seed=True)
    session.expire_all()
    despues = escenas_repo.por_proyecto(session, proy)[1].seed
    assert despues != antes and f"seed {despues}" in log
    assert dict(fake_comfy.llamadas)["generar_imagen"]["seed"] == despues


def test_regenerar_sin_nuevo_seed_conserva_el_seed(session, proy, fake_comfy):
    antes = escenas_repo.por_proyecto(session, proy)[0].seed
    imagenes.regenerar_imagen(proy, 1, nuevo_seed=False)
    assert dict(fake_comfy.llamadas)["generar_imagen"]["seed"] == antes


def test_regenerar_escena_inexistente(session, proy, fake_comfy):
    with pytest.raises(ValueError, match="escena 99"):
        imagenes.regenerar_imagen(proy, 99)
    assert fake_comfy.llamadas == []


# --- retratos ---------------------------------------------------------------

def test_generar_retrato_usa_ficha_y_encuadre(session, dirs_tmp, fake_comfy):
    p = f.proyecto(session)
    f.personaje(session, p.id, ficha="a tall woman with red hair")

    log = retratos.generar_retrato(p.id, "ANA")

    llamada = dict(fake_comfy.llamadas)["generar_imagen"]
    assert llamada["prompt"] == f"a tall woman with red hair, {retratos.ENCUADRE_PERSONA}"
    assert llamada["destino"] == retratos.ruta_retrato("demo", "ANA") and llamada["destino"].exists()
    assert fake_comfy.nombres()[-1] == "liberar_memoria" and "ANA" in log


def test_el_retrato_de_un_objeto_no_pide_cara(session, dirs_tmp, fake_comfy):
    """Regresión: con el encuadre de persona, un mapa descrito con "no humans
    are visible" salía con una cara pintada encima — cinco términos pidiendo
    rostro le ganan a una negación."""
    p = f.proyecto(session)
    ficha = ("a large worn tactical map spread on a wooden table, no humans "
             "are visible")
    f.personaje(session, p.id, clave="MAPA", ficha=ficha, tipo="objeto")

    log = retratos.generar_retrato(p.id, "MAPA")

    prompt = dict(fake_comfy.llamadas)["generar_imagen"]["prompt"]
    assert prompt == f"{ficha}, {retratos.ENCUADRE_OBJETO}"
    for pide_rostro in ("character reference portrait", "sharp focus on the face",
                        "entire head visible", "natural skin texture",
                        "neutral expression"):
        assert pide_rostro not in prompt
    # Y lo niega, que es lo contrario de pedirlo.
    assert "no people" in prompt and "no face" in prompt
    assert "como objeto" in log


@pytest.mark.parametrize("nuevo,cambia", [(False, False), (True, True)])
def test_retrato_nuevo_seed(session, dirs_tmp, fake_comfy, nuevo, cambia):
    p = f.proyecto(session)
    f.personaje(session, p.id)
    retratos.generar_retrato(p.id, "ANA", nuevo_seed=nuevo)
    assert (dict(fake_comfy.llamadas)["generar_imagen"]["seed"] != 1) is cambia


def test_retrato_de_personaje_inexistente_o_sin_ficha(session, dirs_tmp, fake_comfy):
    p = f.proyecto(session)
    with pytest.raises(ValueError, match="ningún personaje"):
        retratos.generar_retrato(p.id, "ANA")
    f.personaje(session, p.id, ficha="   ")
    with pytest.raises(ValueError, match="no tiene ficha"):
        retratos.generar_retrato(p.id, "ANA")
    assert fake_comfy.llamadas == []


# --- retratos de todo el reparto de una tirada ------------------------------

def test_retratos_en_lote_solo_retrata_a_quien_le_falta(session, dirs_tmp, fake_comfy):
    """El autopiloto no puede dar N clics, así que hay una etapa que retrata al
    reparto entero. Quien ya tiene cara no se toca: rehacerla es una decisión, y
    esa cara puede venir del reparto propio o de una serie."""
    p = f.proyecto(session)
    f.personaje(session, p.id, clave="ANA")
    f.personaje(session, p.id, clave="LUIS", nombre="Luis")
    retrato = retratos.ruta_retrato("demo", "ANA")
    retrato.parent.mkdir(parents=True, exist_ok=True)
    retrato.write_bytes(b"png")

    log = retratos.generar_retratos(p.id)

    assert "LUIS" in log and "ANA" not in log
    assert sum(1 for k, _ in fake_comfy.llamadas if k == "generar_imagen") == 1


def test_retratos_en_lote_suelta_la_memoria_una_sola_vez(session, dirs_tmp, fake_comfy):
    """Soltarla tras cada cara descargaría y recargaría ~19 GB por personaje."""
    p = f.proyecto(session)
    f.personaje(session, p.id, clave="ANA")
    f.personaje(session, p.id, clave="LUIS", nombre="Luis")

    retratos.generar_retratos(p.id)

    assert sum(1 for k, _ in fake_comfy.llamadas if k == "liberar_memoria") == 1


def test_retratos_en_lote_sin_reparto_no_hace_nada(session, dirs_tmp, fake_comfy):
    p = f.proyecto(session)

    assert retratos.generar_retratos(p.id) == "Nadie del reparto necesita retrato"
    assert fake_comfy.llamadas == []


def test_un_personaje_sin_ficha_no_cuenta_como_pendiente(session, dirs_tmp):
    """Si contara, el autopiloto pediría una y otra vez una etapa que no puede
    avanzar: sin descripción física no hay nada que dibujar."""
    p = f.proyecto(session)
    f.personaje(session, p.id, clave="ANA", ficha="   ")

    assert retratos.pendientes(session, p.id) == []


def test_retratos_en_lote_se_corta_entre_personajes(session, dirs_tmp, fake_comfy,
                                                    parada_pedida):
    p = f.proyecto(session)
    f.personaje(session, p.id, clave="ANA")

    with pytest.raises(parada.Parado, match="quedaban 1 retratos"):
        retratos.generar_retratos(p.id)
    assert not retratos.ruta_retrato("demo", "ANA").exists()


# --- upscale ----------------------------------------------------------------

def _imagenes(dirs_tmp, ordenes):
    for o in ordenes:
        r = dirs_tmp["proyectos"] / "demo" / "imagenes" / f"{o:02d}.png"
        r.parent.mkdir(parents=True, exist_ok=True)
        r.write_bytes(b"png")


def test_upscale_falla_si_faltan_imagenes(session, proy, fake_comfy, dirs_tmp):
    _imagenes(dirs_tmp, [1, 2])  # las escenas de esta fixture son 1..3
    with pytest.raises(ValueError, match="Faltan imágenes de las escenas \\[3\\]"):
        upscale.generar_upscale(proy)
    assert "upscale_imagen" not in fake_comfy.nombres()


def test_upscale_es_reanudable_y_rehace_solo_lo_viejo(session, dirs_tmp, fake_comfy):
    p = f.proyecto(session)
    escenas_repo.reemplazar_todas(session, p.id, [
        {"orden": o, "t_inicio": 0, "t_fin": 1, "texto": "t", "prompt": "p"} for o in (0, 1, 2)])
    session.commit()
    _imagenes(dirs_tmp, [0, 1, 2])

    assert upscale.generar_upscale(p.id).startswith("3 imágenes reescaladas")
    fake_comfy.llamadas.clear()

    # Sin cambios: no hay nada que hacer, pero igualmente libera la memoria.
    log = upscale.generar_upscale(p.id)
    assert log.startswith("0 imágenes") and "3 ya estaban" in log
    assert "upscale_imagen" not in fake_comfy.nombres()

    # La imagen 1 se regeneró después: solo esa se reescala.
    img = dirs_tmp["proyectos"] / "demo" / "imagenes" / "01.png"
    up = dirs_tmp["proyectos"] / "demo" / "upscale" / "01.png"
    os.utime(img, (up.stat().st_mtime + 100,) * 2)
    fake_comfy.llamadas.clear()
    assert upscale.generar_upscale(p.id).startswith("1 imágenes")
    assert [k["origen"].name for n, k in fake_comfy.llamadas if n == "upscale_imagen"] == ["01.png"]
    session.expire_all()
    assert proyectos_repo.obtener(session, p.id).estado == "UPSCALE"


def test_upscale_sin_escenas(session, dirs_tmp, fake_comfy):
    p = f.proyecto(session)
    with pytest.raises(ValueError, match="no tiene escenas"):
        upscale.generar_upscale(p.id)


def test_el_retrato_del_reparto_no_pasa_por_ningun_proyecto(
    session, dirs_tmp, fake_comfy
):
    """Una serie sabe quiénes son antes del primer capítulo, así que la cara se
    fija ahí: si hubiera que promover desde un proyecto, el episodio 1 se
    inventaría una y los demás heredarían esa."""
    from backend.repositories import reparto as reparto_repo

    m = f.miembro_reparto(session, ficha="a tall woman with red hair")

    log = retratos.generar_retrato_reparto(m.id)

    llamada = dict(fake_comfy.llamadas)["generar_imagen"]
    assert llamada["prompt"] == f"a tall woman with red hair, {retratos.ENCUADRE_PERSONA}"
    assert llamada["destino"] == reparto_repo.ruta_retrato(m.slug)
    assert llamada["destino"].exists()
    session.refresh(m)
    # El seed se queda en el miembro: rehacerle la cara en un proyecto "con el
    # mismo seed" sigue dando esta misma persona.
    assert m.seed and str(m.seed) in log
    assert fake_comfy.nombres()[-1] == "liberar_memoria"


def test_rehacer_la_cara_del_reparto_con_otro_seed_da_otra_persona(
    session, dirs_tmp, fake_comfy
):
    m = f.miembro_reparto(session, ficha="a tall woman with red hair", seed=7)

    retratos.generar_retrato_reparto(m.id, nuevo_seed=True)

    session.refresh(m)
    assert m.seed != 7


def test_sin_ficha_no_hay_nada_que_retratar(session, dirs_tmp, fake_comfy):
    m = f.miembro_reparto(session, ficha="")
    with pytest.raises(ValueError, match="ficha"):
        retratos.generar_retrato_reparto(m.id)
    with pytest.raises(ValueError, match="reparto"):
        retratos.generar_retrato_reparto(999)
    assert fake_comfy.llamadas == []
