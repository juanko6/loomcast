"""El reparto propio: promover, traer, actualizar y borrar."""
import pytest

from backend.repositories import personajes as personajes_repo
from backend.repositories import reparto as reparto_repo
from tests import factories as f

pytestmark = pytest.mark.integration

FICHA = "a tall woman with red hair"


@pytest.fixture
def proy(session, dirs_tmp):
    return f.proyecto(session)


def _retrato_proyecto(dirs_tmp, clave, slug="demo", contenido=b"png"):
    ruta = dirs_tmp["proyectos"] / slug / "personajes" / f"{clave}.png"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


def _retrato_reparto(dirs_tmp, slug, contenido=b"png"):
    ruta = dirs_tmp["reparto"] / slug / "retrato.png"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


# --- listado ----------------------------------------------------------------

def test_listar_vacio(client):
    assert client.get("/api/reparto").json() == []


def test_listar_dice_quien_tiene_cara(client, session, dirs_tmp):
    f.miembro_reparto(session)
    assert client.get("/api/reparto").json() == [
        {"slug": "ana-narradora", "nombre": "Ana narradora", "clave": "ANA",
         "ficha": FICHA, "tipo": "persona", "voz": "", "retrato": False}]
    _retrato_reparto(dirs_tmp, "ana-narradora")
    assert client.get("/api/reparto").json()[0]["retrato"] is True


# --- promover ---------------------------------------------------------------

def test_promover_copia_la_cara_y_deja_enlazado_al_personaje(client, session, proy, dirs_tmp):
    f.personaje(session, proy.id, tipo="persona")
    _retrato_proyecto(dirs_tmp, "ANA", contenido=b"cara")

    r = client.post("/api/reparto", json={"proyecto_id": proy.id, "clave": "ANA",
                                          "nombre": "Ana narradora"})

    assert r.json() == {"slug": "ana-narradora", "nombre": "Ana narradora",
                        "retrato": True}
    # El retrato es una COPIA: el proyecto es autocontenido y sigue teniendo el suyo.
    assert (dirs_tmp["reparto"] / "ana-narradora" / "retrato.png").read_bytes() == b"cara"
    assert _retrato_proyecto(dirs_tmp, "ANA", contenido=b"cara").exists()
    session.expire_all()
    m = reparto_repo.por_slug(session, "ana-narradora")
    assert (m.clave, m.ficha, m.tipo, m.seed) == ("ANA", FICHA, "persona", 1)
    assert personajes_repo.por_proyecto(session, proy.id)[0].reparto_slug == "ana-narradora"


def test_promover_sin_nombre_usa_el_del_proyecto(client, session, proy, dirs_tmp):
    f.personaje(session, proy.id, nombre="Ana")
    assert client.post("/api/reparto", json={"proyecto_id": proy.id, "clave": "ANA"}).json() == {
        "slug": "ana", "nombre": "Ana", "retrato": False}


def test_promover_un_objeto_se_lleva_su_tipo(client, session, proy, dirs_tmp):
    """El tipo viaja con el miembro: si no, al traerlo se le retrataría con
    encuadre de persona y el generador le pintaría una cara encima."""
    f.personaje(session, proy.id, clave="MAPA", nombre="El mapa",
                ficha="a worn tactical map, no humans are visible", tipo="objeto")

    client.post("/api/reparto", json={"proyecto_id": proy.id, "clave": "MAPA"})

    session.expire_all()
    assert reparto_repo.por_slug(session, "el-mapa").tipo == "objeto"


def test_promover_sin_ficha_400(client, session, proy, dirs_tmp):
    f.personaje(session, proy.id, ficha="   ")
    r = client.post("/api/reparto", json={"proyecto_id": proy.id, "clave": "ANA"})
    assert r.status_code == 400 and "ficha" in r.json()["detail"]


def test_promover_con_nombre_ya_usado_409(client, session, proy, dirs_tmp):
    f.miembro_reparto(session, slug="ana", nombre="Ana")
    f.personaje(session, proy.id, nombre="ANA!")
    assert client.post("/api/reparto",
                       json={"proyecto_id": proy.id, "clave": "ANA"}).status_code == 409


def test_promover_entrada_invalida(client, session, proy, dirs_tmp):
    f.personaje(session, proy.id)
    casos = [
        ({"proyecto_id": 99, "clave": "ANA"}, 404),        # proyecto que no existe
        ({"proyecto_id": proy.id, "clave": "NADIE"}, 404),  # no está en el reparto
        ({"proyecto_id": proy.id, "clave": ""}, 422),       # clave vacía
    ]
    assert [client.post("/api/reparto", json=c).status_code for c, _ in casos] == \
        [codigo for _, codigo in casos]


# --- traer ------------------------------------------------------------------

def test_traer_mete_al_miembro_con_su_cara_copiada(client, session, proy, dirs_tmp):
    f.miembro_reparto(session, seed=42)
    _retrato_reparto(dirs_tmp, "ana-narradora", contenido=b"cara")

    r = client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})

    assert r.json() == {"clave": "ANA", "renombrado": False, "retrato": True,
                        "voz": ""}
    assert (dirs_tmp["proyectos"] / "demo" / "personajes" / "ANA.png").read_bytes() == b"cara"
    session.expire_all()
    p = personajes_repo.por_proyecto(session, proy.id)[0]
    assert (p.clave, p.ficha, p.tipo, p.seed, p.reparto_slug) == (
        "ANA", FICHA, "persona", 42, "ana-narradora")


def test_traer_a_alguien_sin_cara_guardada_lo_mete_igual(client, session, proy, dirs_tmp):
    f.miembro_reparto(session)
    r = client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})
    assert r.json()["retrato"] is False
    assert personajes_repo.existe(session, proy.id, "ANA")


def test_traer_con_la_clave_ocupada_no_pisa_al_que_estaba(client, session, proy, dirs_tmp):
    """Las claves son marcadores {CLAVE} ya escritos en los prompts: dos con el
    mismo marcador harían que el segundo se quedara con la ficha del primero."""
    f.personaje(session, proy.id, clave="ANA", nombre="otra Ana", ficha="a short blonde woman")
    _retrato_proyecto(dirs_tmp, "ANA", contenido=b"la de antes")
    f.miembro_reparto(session)
    _retrato_reparto(dirs_tmp, "ana-narradora", contenido=b"la del reparto")

    r = client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})

    assert r.json() == {"clave": "ANA_2", "renombrado": True, "retrato": True,
                        "voz": ""}
    session.expire_all()
    ps = personajes_repo.por_proyecto(session, proy.id)
    assert [(x.clave, x.ficha) for x in ps] == [
        ("ANA", "a short blonde woman"), ("ANA_2", FICHA)]
    carpeta = dirs_tmp["proyectos"] / "demo" / "personajes"
    assert (carpeta / "ANA.png").read_bytes() == b"la de antes"
    assert (carpeta / "ANA_2.png").read_bytes() == b"la del reparto"


def test_traer_dos_veces_al_mismo_va_numerando(client, session, proy, dirs_tmp):
    f.miembro_reparto(session)
    claves = [
        client.post("/api/reparto/ana-narradora/traer",
                    json={"proyecto_id": proy.id}).json()["clave"]
        for _ in range(3)
    ]
    assert claves == ["ANA", "ANA_2", "ANA_3"]


def test_traer_de_un_miembro_o_proyecto_inexistente_404(client, session, proy, dirs_tmp):
    assert client.post("/api/reparto/nadie/traer",
                       json={"proyecto_id": proy.id}).status_code == 404
    f.miembro_reparto(session)
    assert client.post("/api/reparto/ana-narradora/traer",
                       json={"proyecto_id": 99}).status_code == 404


# --- editar en el proyecto sin contaminar el original -----------------------

def test_editar_la_ficha_en_el_proyecto_no_toca_al_original(client, session, proy, dirs_tmp):
    """Un retoque para una escena no puede cambiar al personaje en todos los
    vídeos futuros: para eso está "actualizar en el reparto"."""
    f.miembro_reparto(session)
    client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})

    client.put(f"/api/proyectos/{proy.id}/casting", json={"personajes": [
        {"clave": "ANA", "nombre": "Ana retocada", "ficha": "a woman with short grey hair"}]})

    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].ficha == "a woman with short grey hair"
    m = reparto_repo.por_slug(session, "ana-narradora")
    assert (m.ficha, m.nombre) == (FICHA, "Ana narradora")


def test_actualizar_sube_la_version_del_proyecto_al_reparto(client, session, proy, dirs_tmp):
    f.miembro_reparto(session)
    _retrato_reparto(dirs_tmp, "ana-narradora", contenido=b"vieja")
    client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})
    client.put(f"/api/proyectos/{proy.id}/casting", json={"personajes": [
        {"clave": "ANA", "nombre": "Ana", "ficha": "a woman with short grey hair"}]})
    _retrato_proyecto(dirs_tmp, "ANA", contenido=b"nueva")

    r = client.put("/api/reparto/ana-narradora",
                   json={"proyecto_id": proy.id, "clave": "ANA"})

    assert r.json() == {"slug": "ana-narradora", "nombre": "Ana narradora",
                        "retrato": True}
    session.expire_all()
    assert reparto_repo.por_slug(session, "ana-narradora").ficha == "a woman with short grey hair"
    assert (dirs_tmp["reparto"] / "ana-narradora" / "retrato.png").read_bytes() == b"nueva"


def test_actualizar_desde_un_personaje_que_no_vino_del_reparto(client, session, proy, dirs_tmp):
    """Vale apuntar a cualquier personaje del proyecto: queda enlazado a ese
    miembro, que es lo que se acaba de pedir."""
    f.miembro_reparto(session)
    f.personaje(session, proy.id, clave="LUIS", ficha="a bald man with a scar")

    client.put("/api/reparto/ana-narradora", json={"proyecto_id": proy.id, "clave": "LUIS"})

    session.expire_all()
    m = reparto_repo.por_slug(session, "ana-narradora")
    assert (m.ficha, m.clave) == ("a bald man with a scar", "LUIS")
    assert personajes_repo.por_proyecto(session, proy.id)[0].reparto_slug == "ana-narradora"


def test_actualizar_inexistente_404(client, session, proy, dirs_tmp):
    f.personaje(session, proy.id)
    assert client.put("/api/reparto/nadie",
                      json={"proyecto_id": proy.id, "clave": "ANA"}).status_code == 404
    f.miembro_reparto(session)
    assert client.put("/api/reparto/ana-narradora",
                      json={"proyecto_id": proy.id, "clave": "NADIE"}).status_code == 404


# --- la voz viaja con el miembro --------------------------------------------

def _voz(session, slug="ana-voz"):
    from backend.repositories import voces as voces_repo

    v = voces_repo.crear(session, slug, slug, "grave")
    v.estado = "lista"
    session.commit()
    return v


def test_promover_se_lleva_la_voz_del_personaje(client, session, proy, dirs_tmp):
    """La voz va con la ficha y la cara: un narrador recurrente que ya sonaba
    bien no tiene por qué volver a sonar distinto en el vídeo siguiente."""
    _voz(session)
    f.personaje(session, proy.id, voz="ana-voz")

    client.post("/api/reparto", json={"proyecto_id": proy.id, "clave": "ANA",
                                      "nombre": "Ana narradora"})

    session.expire_all()
    assert reparto_repo.por_slug(session, "ana-narradora").voz == "ana-voz"


def test_traer_mete_al_miembro_con_su_voz(client, session, proy, dirs_tmp):
    _voz(session)
    f.miembro_reparto(session, voz="ana-voz")

    r = client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})

    assert r.json()["voz"] == "ana-voz"
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].voz == "ana-voz"


def test_traer_con_la_voz_borrada_del_banco_entra_sin_voz(client, session, proy, dirs_tmp):
    """La voz del reparto NO se copia como el retrato: es una fila del banco,
    compartida. Si se borró de allí, apuntar a su `ref.wav` dejaría las líneas
    mudas sin decir por qué."""
    f.miembro_reparto(session, voz="fantasma")

    r = client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})

    assert r.json()["voz"] == ""
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].voz == ""


def test_actualizar_sube_tambien_la_voz(client, session, proy, dirs_tmp):
    _voz(session, "otra-voz")
    f.miembro_reparto(session, voz="ana-voz")
    client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})
    client.put(f"/api/proyectos/{proy.id}/personajes/ANA/voz", json={"voz": "otra-voz"})

    client.put("/api/reparto/ana-narradora",
               json={"proyecto_id": proy.id, "clave": "ANA"})

    session.expire_all()
    assert reparto_repo.por_slug(session, "ana-narradora").voz == "otra-voz"


# --- borrar y retrato -------------------------------------------------------

def test_borrar_no_rompe_los_proyectos_que_ya_se_lo_trajeron(client, session, proy, dirs_tmp):
    f.miembro_reparto(session)
    _retrato_reparto(dirs_tmp, "ana-narradora", contenido=b"cara")
    client.post("/api/reparto/ana-narradora/traer", json={"proyecto_id": proy.id})

    r = client.delete("/api/reparto/ana-narradora")

    assert r.json() == {"slug": "ana-narradora", "personajes_desvinculados": 1}
    assert not (dirs_tmp["reparto"] / "ana-narradora").exists()
    session.expire_all()
    p = personajes_repo.por_proyecto(session, proy.id)[0]
    # La ficha y la cara del proyecto siguen ahí: eran copias, no referencias.
    assert (p.ficha, p.reparto_slug) == (FICHA, "")
    assert (dirs_tmp["proyectos"] / "demo" / "personajes" / "ANA.png").read_bytes() == b"cara"


def test_borrar_inexistente_404(client):
    assert client.delete("/api/reparto/nadie").status_code == 404


def test_retrato_del_reparto(client, session, dirs_tmp):
    assert client.get("/api/reparto/ana-narradora/retrato").status_code == 404
    f.miembro_reparto(session)
    assert client.get("/api/reparto/ana-narradora/retrato").status_code == 404  # sin cara aún
    _retrato_reparto(dirs_tmp, "ana-narradora", contenido=b"png")
    r = client.get("/api/reparto/ana-narradora/retrato")
    assert r.status_code == 200 and r.content == b"png"
