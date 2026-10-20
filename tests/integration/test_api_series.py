"""Series: crear, reparto fijo, episodios que heredan y borrados sin huérfanos."""
import pytest

from backend.models import Proyecto, SerieMiembro
from backend.repositories import personajes as personajes_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import series as series_repo
from backend.repositories import temas as temas_repo
from tests import factories as f

pytestmark = pytest.mark.integration

FICHA = "a tall woman with red hair"


def _crear(client, nombre="La casa de Alicia", plantilla="serie"):
    r = client.post("/api/series", json={"nombre": nombre, "plantilla": plantilla})
    assert r.status_code == 200, r.text
    return r.json()


def _retrato_reparto(dirs_tmp, slug, contenido=b"cara"):
    ruta = dirs_tmp["reparto"] / slug / "retrato.png"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


# --- crear ------------------------------------------------------------------

def test_crear_serie_crea_su_tema_de_ideas_de_episodio(client, session):
    s = _crear(client)

    assert s["slug"] == "la-casa-de-alicia" and s["plantilla"] == "serie"
    assert (s["n_episodios"], s["n_miembros"]) == (0, 0)
    # El tema es suyo: de ahí cuelgan las ideas de episodio, y aprobar una de
    # ellas crea el episodio siguiente.
    tema = temas_repo.obtener(session, s["tema_id"])
    assert (tema.texto, tema.plantilla) == ("La casa de Alicia", "serie")
    assert series_repo.por_tema(session, tema.id).id == s["id"]


def test_crear_serie_con_plantilla_desconocida_400(client):
    r = client.post("/api/series", json={"nombre": "X", "plantilla": "no_existe"})
    assert r.status_code == 400


def test_dos_series_con_el_mismo_nombre_409(client):
    _crear(client)
    assert client.post(
        "/api/series", json={"nombre": "La casa de Alicia"}).status_code == 409


def test_listar_y_detalle(client, session):
    s = _crear(client)
    assert client.get("/api/series").json()[0]["nombre"] == "La casa de Alicia"
    d = client.get(f"/api/series/{s['id']}").json()
    assert d["miembros"] == [] and d["episodios"] == []
    assert client.get("/api/series/999").status_code == 404


# --- reparto fijo -----------------------------------------------------------

def test_anadir_y_quitar_miembro_del_reparto_fijo(client, session, dirs_tmp):
    s = _crear(client)
    f.miembro_reparto(session)
    _retrato_reparto(dirs_tmp, "ana-narradora")

    assert client.post(f"/api/series/{s['id']}/miembros",
                       json={"reparto_slug": "ana-narradora"}).status_code == 200

    d = client.get(f"/api/series/{s['id']}").json()
    assert d["n_miembros"] == 1
    assert d["miembros"] == [
        {"slug": "ana-narradora", "nombre": "Ana narradora", "clave": "ANA",
         "ficha": FICHA, "tipo": "persona", "voz": "", "retrato": True}]

    assert client.delete(
        f"/api/series/{s['id']}/miembros/ana-narradora").status_code == 200
    assert client.get(f"/api/series/{s['id']}").json()["miembros"] == []


def test_miembro_repetido_409_y_desconocido_404(client, session):
    s = _crear(client)
    f.miembro_reparto(session)
    client.post(f"/api/series/{s['id']}/miembros", json={"reparto_slug": "ana-narradora"})
    assert client.post(f"/api/series/{s['id']}/miembros",
                       json={"reparto_slug": "ana-narradora"}).status_code == 409
    assert client.post(f"/api/series/{s['id']}/miembros",
                       json={"reparto_slug": "nadie"}).status_code == 404
    assert client.delete(
        f"/api/series/{s['id']}/miembros/nadie").status_code == 404


def test_borrar_del_reparto_propio_lo_saca_de_las_series(client, session, dirs_tmp):
    """Estas filas son la orden de traerlo a cada episodio nuevo: dejarlas haría
    fallar la creación del siguiente episodio con alguien que ya no existe."""
    s = _crear(client)
    f.miembro_reparto(session)
    client.post(f"/api/series/{s['id']}/miembros", json={"reparto_slug": "ana-narradora"})

    r = client.delete("/api/reparto/ana-narradora")

    assert r.json()["series_desvinculadas"] == 1
    session.expire_all()
    assert series_repo.miembros(session, s["id"]) == []


# --- episodios --------------------------------------------------------------

def test_nuevo_episodio_numera_hereda_la_plantilla_y_encola_el_guion(
    client, session, dirs_tmp, jobs_encolados
):
    s = _crear(client)

    r = client.post(f"/api/series/{s['id']}/episodios", json={"apunte": ""}).json()

    assert r["episodio"] == 1
    session.expire_all()
    p = proyectos_repo.obtener(session, r["proyecto_id"])
    assert (p.serie_id, p.episodio, p.plantilla) == (s["id"], 1, "serie")
    assert p.resumen_episodio == ""
    assert jobs_encolados == [("generar_guion", p.id)]

    segundo = client.post(f"/api/series/{s['id']}/episodios").json()
    assert segundo["episodio"] == 2


def test_el_apunte_entra_como_resumen_de_la_idea(client, session, dirs_tmp):
    """Es el campo que el prompt de guion ya lee: sin apunte, el episodio lo
    propone el LLM desde el resumen del anterior."""
    from backend.repositories import ideas as ideas_repo

    s = _crear(client)
    r = client.post(f"/api/series/{s['id']}/episodios",
                    json={"apunte": "Ana encuentra la llave"}).json()
    idea = ideas_repo.obtener(session, r["idea_id"])
    assert idea.titulo == "Episodio 1: Ana encuentra la llave"
    assert idea.resumen == "Ana encuentra la llave"
    assert idea.estado == "aprobada"


def test_el_episodio_se_trae_el_reparto_fijo_con_su_cara_y_su_voz(
    client, session, dirs_tmp
):
    s = _crear(client)
    from backend.repositories import voces as voces_repo

    voces_repo.crear(session, "voz-ana", "Voz de Ana", "instruct")
    f.miembro_reparto(session, voz="voz-ana")
    _retrato_reparto(dirs_tmp, "ana-narradora", contenido=b"cara")
    client.post(f"/api/series/{s['id']}/miembros", json={"reparto_slug": "ana-narradora"})

    r = client.post(f"/api/series/{s['id']}/episodios").json()

    assert r["reparto_traido"] == ["ANA"]
    session.expire_all()
    p = proyectos_repo.obtener(session, r["proyecto_id"])
    personaje = personajes_repo.por_proyecto(session, p.id)[0]
    # Ficha, tipo, seed y voz viajan; la cara se COPIA a la carpeta del
    # proyecto, que es lo que lo deja autocontenido.
    assert (personaje.clave, personaje.ficha, personaje.voz) == ("ANA", FICHA, "voz-ana")
    assert personaje.reparto_slug == "ana-narradora"
    retrato = dirs_tmp["proyectos"] / p.slug / "personajes" / "ANA.png"
    assert retrato.read_bytes() == b"cara"


def test_dos_miembros_con_la_misma_clave_entran_numerados(client, session, dirs_tmp):
    """Las claves son marcadores {CLAVE} ya escritos en los prompts: el segundo
    no puede pisar al primero, así que entra como ANA_2."""
    s = _crear(client)
    f.miembro_reparto(session)
    f.miembro_reparto(session, slug="ana-vecina", nombre="Ana la vecina", clave="ANA",
                      ficha="a short woman with grey hair")
    for slug in ("ana-narradora", "ana-vecina"):
        client.post(f"/api/series/{s['id']}/miembros", json={"reparto_slug": slug})

    r = client.post(f"/api/series/{s['id']}/episodios").json()

    assert r["reparto_traido"] == ["ANA", "ANA_2"]
    session.expire_all()
    claves = [x.clave for x in
              personajes_repo.por_proyecto(session, r["proyecto_id"])]
    assert claves == ["ANA", "ANA_2"]


def test_aprobar_una_idea_del_tema_de_la_serie_crea_el_episodio_siguiente(
    client, session, dirs_tmp
):
    """El otro camino, con el mismo mecanismo: las ideas de episodio son ideas
    del tema de la serie, y aprobar una de ellas hereda la serie."""
    s = _crear(client)
    f.miembro_reparto(session)
    client.post(f"/api/series/{s['id']}/miembros", json={"reparto_slug": "ana-narradora"})
    f.episodio(session, series_repo.obtener(session, s["id"]), numero=1)
    idea = f.idea(session, s["tema_id"], titulo="El sobre")

    r = client.post(f"/api/ideas/{idea.id}/proyecto").json()

    session.expire_all()
    p = proyectos_repo.obtener(session, r["proyecto_id"])
    assert (p.serie_id, p.episodio) == (s["id"], 2)
    assert r["reparto_traido"] == ["ANA"]


def test_un_proyecto_de_un_tema_sin_serie_no_cambia_en_nada(
    client, session, dirs_tmp, jobs_encolados
):
    """La prueba que importa: con series en la base, un vídeo suelto sigue
    siendo exactamente lo que era."""
    _crear(client)  # hay una serie, con su reparto fijo vacío, en la base
    tema = f.tema(session, texto="misterios del océano", plantilla="curiosidades")
    idea = f.idea(session, tema.id, titulo="Una idea")

    r = client.post(f"/api/ideas/{idea.id}/proyecto").json()

    session.expire_all()
    p = proyectos_repo.obtener(session, r["proyecto_id"])
    assert (p.serie_id, p.episodio, p.resumen_episodio) == (None, 0, "")
    assert p.plantilla == "curiosidades"
    assert r["reparto_traido"] == []
    assert jobs_encolados == [("generar_guion", p.id)]
    d = client.get(f"/api/proyectos/{p.id}").json()
    assert d["serie"] is None and d["resumen_episodio"] == ""


def test_el_detalle_del_episodio_trae_la_serie_y_el_resumen_anterior(
    client, session, dirs_tmp
):
    s = _crear(client)
    serie = series_repo.obtener(session, s["id"])
    f.episodio(session, serie, numero=1, resumen="Alicia encontró la llave.")
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")

    d = client.get(f"/api/proyectos/{ep2.id}").json()

    assert d["serie"] == {
        "id": s["id"], "nombre": "La casa de Alicia", "slug": "la-casa-de-alicia",
        "episodio": 2,
        "anterior": {"episodio": 1, "resumen": "Alicia encontró la llave."}}
    assert client.get("/api/proyectos").json()[0]["serie"] == "La casa de Alicia"


def test_editar_el_resumen_del_episodio(client, session, dirs_tmp):
    s = _crear(client)
    ep = f.episodio(session, series_repo.obtener(session, s["id"]))

    r = client.put(f"/api/proyectos/{ep.id}/resumen",
                   json={"resumen": "  Alicia abre la puerta.  "})

    assert r.json() == {"resumen": "Alicia abre la puerta."}
    session.expire_all()
    assert proyectos_repo.obtener(session, ep.id).resumen_episodio == (
        "Alicia abre la puerta.")


def test_el_resumen_solo_existe_para_los_episodios(client, session, dirs_tmp):
    suelto = f.proyecto(session)
    r = client.put(f"/api/proyectos/{suelto.id}/resumen", json={"resumen": "x"})
    assert r.status_code == 400 and "episodio" in r.text


# --- borrados ---------------------------------------------------------------

def test_borrar_la_serie_suelta_sus_episodios_y_no_deja_huerfanos(
    client, session, dirs_tmp
):
    s = _crear(client)
    f.miembro_reparto(session)
    client.post(f"/api/series/{s['id']}/miembros", json={"reparto_slug": "ana-narradora"})
    serie = series_repo.obtener(session, s["id"])
    ep1 = f.episodio(session, serie, numero=1)
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")

    r = client.delete(f"/api/series/{s['id']}")

    assert r.json() == {"episodios_sueltos": 2}
    session.expire_all()
    # Los episodios NO se borran: llevan su guion, su voz y su vídeo. Se quedan
    # como vídeos sueltos, que es lo que son sin serie.
    for ep in (ep1, ep2):
        p = proyectos_repo.obtener(session, ep.id)
        assert p is not None and (p.serie_id, p.episodio) == (None, 0)
    assert session.query(SerieMiembro).count() == 0
    assert series_repo.obtener(session, s["id"]) is None
    # El tema de las ideas de episodio sigue siendo un tema normal.
    assert temas_repo.obtener(session, s["tema_id"]) is not None
    assert client.delete(f"/api/series/{s['id']}").status_code == 404


def test_borrar_un_episodio_no_rompe_los_demas(client, session, dirs_tmp):
    s = _crear(client)
    serie = series_repo.obtener(session, s["id"])
    f.episodio(session, serie, numero=1, resumen="Pasó esto.")
    ep2 = f.episodio(session, serie, numero=2, slug="ep-2")
    f.episodio(session, serie, numero=3, slug="ep-3")

    assert client.delete(f"/api/proyectos/{ep2.id}").status_code == 200

    session.expire_all()
    assert [p.episodio for p in series_repo.episodios(session, s["id"])] == [1, 3]
    # El 3 continúa el 1: lo que importa es de dónde viene la historia, no la
    # numeración. Y el próximo sigue siendo el 4, no el 3 otra vez.
    assert series_repo.anterior(session, s["id"], 3).episodio == 1
    assert series_repo.siguiente_numero(session, s["id"]) == 4
    assert client.get(f"/api/series/{s['id']}").json()["n_episodios"] == 2


def test_el_listado_de_episodios_dice_cuales_estan_cerrados(client, session, dirs_tmp):
    s = _crear(client)
    serie = series_repo.obtener(session, s["id"])
    f.episodio(session, serie, numero=1, resumen="Pasó esto.", titulo="El sobre")
    f.episodio(session, serie, numero=2, slug="ep-2")

    episodios = client.get(f"/api/series/{s['id']}").json()["episodios"]

    assert [(e["episodio"], e["titulo"], bool(e["resumen"]), e["ocupado"])
            for e in episodios] == [(1, "El sobre", True, False),
                                    (2, "Episodio 2", False, False)]


def test_series_sin_filas_no_molestan_al_resto(client, session, engine):
    """La tabla nueva no cambia nada si nadie la usa: el único test que lo dice
    de la propia base."""
    assert session.query(Proyecto).filter(Proyecto.serie_id.isnot(None)).count() == 0
    assert client.get("/api/series").json() == []


def test_el_tema_de_la_serie_se_marca_como_suyo_en_el_listado(client, session):
    """La UI no lo lista aparte: tiene el mismo nombre que la serie y se entra a
    sus ideas de episodio desde ella."""
    s = _crear(client)
    f.tema(session, texto="misterios del océano")

    temas = {t["texto"]: t["serie"] for t in client.get("/api/temas").json()}

    assert temas == {"La casa de Alicia": "La casa de Alicia",
                     "misterios del océano": None}
