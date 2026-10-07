import os

import pytest

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
    assert llamada["prompt"] == f"a tall woman with red hair, {retratos.ENCUADRE}"
    assert llamada["destino"] == retratos.ruta_retrato("demo", "ANA") and llamada["destino"].exists()
    assert fake_comfy.nombres()[-1] == "liberar_memoria" and "ANA" in log


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
