import json

import pytest

from backend.models import Job, Voz
from backend.repositories import escenas as escenas_repo
from backend.repositories import guiones as guiones_repo
from backend.repositories import personajes as personajes_repo
from backend.repositories import proyectos as proyectos_repo
from tests import factories as f

pytestmark = pytest.mark.integration


@pytest.fixture
def proy(session, dirs_tmp):
    return f.proyecto(session)


def _archivo(dirs_tmp, *partes, contenido=b"x"):
    ruta = dirs_tmp["proyectos"].joinpath("demo", *partes)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


# --- listado y detalle ------------------------------------------------------

def test_listar_vacio(client):
    assert client.get("/api/proyectos").json() == []


def test_listar_incluye_titulo_de_la_idea(client, proy):
    assert client.get("/api/proyectos").json() == [
        {"id": proy.id, "slug": "demo", "estado": "IDEA",
         "plantilla": "curiosidades", "titulo": "Una idea",
         # Un vídeo suelto: sin serie y sin número de episodio.
         "serie": None, "episodio": 0,
         # Y sin autopiloto: se conduce a mano, como siempre.
         "autopiloto": None,
         # Ni subido a ninguna parte.
         "publicado_en": ""}]


def test_detalle_inexistente_404(client):
    assert client.get("/api/proyectos/99").status_code == 404


def test_detalle_de_proyecto_recien_creado(client, proy):
    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["guion"] is None and d["metadatos"] is None and d["subtitulos"] is None
    assert d["escenas"] == [] and d["personajes"] == []
    assert d["voz_disponible"] is False and d["video_disponible"] is False
    assert d["imagenes_completas"] is False and d["job_activo"] is None
    # Sin guion, el instruct de voz sale de la plantilla.
    assert d["voz_instruct"].startswith("Voz masculina")


def test_detalle_refleja_archivos_en_disco_y_jobs_activos(client, session, proy, dirs_tmp):
    f.escenas(session, proy.id, n=2)
    f.personaje(session, proy.id)
    guiones_repo.crear(session, proy.id, {"gancho": "G", "voz_instruct": "mi voz"})
    session.add(Job(tipo="generar_voz", ref_id=proy.id, estado="corriendo"))
    session.commit()
    _archivo(dirs_tmp, "voz.mp3")
    _archivo(dirs_tmp, "subtitulos.srt", contenido=b"1\nhola")
    _archivo(dirs_tmp, "imagenes", "01.png")
    _archivo(dirs_tmp, "imagenes", "02.png")
    _archivo(dirs_tmp, "final.mp4")
    _archivo(dirs_tmp, "versiones", "final_20260101.mp4")

    d = client.get(f"/api/proyectos/{proy.id}").json()

    assert d["voz_disponible"] and d["video_disponible"] and d["imagenes_completas"]
    assert d["subtitulos"] == "1\nhola"
    assert d["voz_instruct"] == "mi voz"
    assert d["guion_version"] == 1
    assert [e["imagen"] for e in d["escenas"]] == [True, True]
    assert d["personajes"] == [
        {"clave": "ANA", "nombre": "Ana", "ficha": "a tall woman with red hair",
         "tipo": "persona", "reparto_slug": "", "voz": "", "retrato": False}]
    assert d["versiones"][0]["nombre"] == "final_20260101.mp4"
    assert d["job_activo"] == "generar_voz" and d["jobs_activos"] == 1


# --- guion ------------------------------------------------------------------

def test_editar_guion_crea_version_y_avanza_estado(client, session, proy):
    r = client.put(f"/api/proyectos/{proy.id}/guion",
                   json={"gancho": "G", "frases": ["a", "b"], "cta": "C"})
    assert r.json() == {"version": 1}
    r = client.put(f"/api/proyectos/{proy.id}/guion", json={"narracion": "texto"})
    assert r.json() == {"version": 2}
    session.expire_all()
    assert proyectos_repo.obtener(session, proy.id).estado == "GUION"


def test_editar_guion_conserva_el_voz_instruct_previo(client, session, proy):
    guiones_repo.crear(session, proy.id, {"gancho": "G", "voz_instruct": "heredada"})
    session.commit()
    client.put(f"/api/proyectos/{proy.id}/guion", json={"gancho": "nuevo"})
    session.expire_all()
    assert json.loads(guiones_repo.ultimo(session, proy.id).contenido)["voz_instruct"] == "heredada"


def test_el_detalle_devuelve_la_linea_sin_el_nombre_delante(client, session, proy):
    """El guion se guardó con el nombre dentro del texto ("ANA ¿y si…"), que es
    lo que el LLM escribe de vez en cuando y lo que se oía en el audio. La
    etapa de voz ya no lo narra, así que el editor tampoco puede enseñarlo."""
    guiones_repo.crear(session, proy.id, {
        "gancho": "G",
        "lineas": [{"personaje": "ANA", "texto": "ANA ¿y si soy yo?"}],
    })
    session.commit()
    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["guion"]["lineas"] == [{"personaje": "ANA", "texto": "¿y si soy yo?"}]


def test_editar_guion_de_proyecto_inexistente_404(client):
    assert client.put("/api/proyectos/99/guion", json={}).status_code == 404


def test_editar_guion_con_tipos_invalidos_422(client, proy):
    assert client.put(f"/api/proyectos/{proy.id}/guion", json={"frases": "no-lista"}).status_code == 422


# --- etapas que solo encolan -----------------------------------------------

@pytest.mark.parametrize("ruta,tipo", [
    ("guion/regenerar", "generar_guion"),
    ("metadatos", "generar_metadatos"),
    ("subtitulos", "generar_subtitulos"),
    ("casting", "generar_casting"),
    ("escenas", "generar_escenas"),
    ("imagenes", "generar_imagenes"),
])
def test_etapas_simples_encolan_su_job(client, proy, jobs_encolados, ruta, tipo):
    r = client.post(f"/api/proyectos/{proy.id}/{ruta}")
    assert r.status_code == 200 and "job_id" in r.json()
    assert jobs_encolados == [(tipo, proy.id)]


def test_generar_voz_pasa_modo_e_instruct(client, proy, jobs_encolados):
    client.post(f"/api/proyectos/{proy.id}/voz", json={"modo": "design", "instruct": "grave"})
    client.post(f"/api/proyectos/{proy.id}/voz")
    assert jobs_encolados.params == [
        {"modo": "design", "instruct": "grave"}, {"modo": "clon", "instruct": None}]


def test_regenerar_imagen_y_clip_de_una_escena(client, proy, jobs_encolados):
    client.post(f"/api/proyectos/{proy.id}/escenas/3/imagen", json={})
    client.post(f"/api/proyectos/{proy.id}/escenas/3/clip", json={"modo": "i2v"})
    assert jobs_encolados == [("regenerar_imagen", proy.id), ("regenerar_clip", proy.id)]
    assert jobs_encolados.params == [
        {"orden": 3, "nuevo_seed": True}, {"orden": 3, "modo": "i2v"}]


# --- voz del proyecto -------------------------------------------------------

def test_seleccionar_voz(client, session, proy):
    session.add(Voz(slug="ana", nombre="Ana", instruct="x"))
    session.commit()
    assert client.put(f"/api/proyectos/{proy.id}/voz", json={"voz": "ana"}).json() == {"ok": True}
    session.expire_all()
    assert proyectos_repo.obtener(session, proy.id).voz == "ana"


def test_seleccionar_voz_inexistente_400(client, proy):
    assert client.put(f"/api/proyectos/{proy.id}/voz", json={"voz": "nadie"}).status_code == 400


def test_seleccionar_voz_en_proyecto_inexistente_404(client):
    assert client.put("/api/proyectos/99/voz", json={"voz": "x"}).status_code == 404


# --- personajes y casting ---------------------------------------------------

def test_anadir_personaje_normaliza_la_clave(client, session, proy):
    r = client.post(f"/api/proyectos/{proy.id}/personajes",
                    json={"clave": " el escritor  raro ", "nombre": " Raro ", "ficha": " f "})
    assert r.json() == {"clave": "EL_ESCRITOR_RARO"}
    session.expire_all()
    p = personajes_repo.por_proyecto(session, proy.id)[0]
    assert (p.nombre, p.ficha) == ("Raro", "f")


def test_anadir_personaje_repetido_409(client, session, proy):
    f.personaje(session, proy.id, clave="ANA")
    r = client.post(f"/api/proyectos/{proy.id}/personajes", json={"clave": "ana"})
    assert r.status_code == 409


@pytest.mark.parametrize("clave", ["!!!", "   ", "¿?"])
def test_anadir_personaje_con_clave_que_queda_vacia_400(client, proy, clave):
    assert client.post(f"/api/proyectos/{proy.id}/personajes", json={"clave": clave}).status_code == 400


def test_anadir_personaje_clave_demasiado_larga_422(client, proy):
    assert client.post(f"/api/proyectos/{proy.id}/personajes", json={"clave": "A" * 25}).status_code == 422


def test_anadir_personaje_a_proyecto_inexistente_404(client):
    assert client.post("/api/proyectos/99/personajes", json={"clave": "ANA"}).status_code == 404


def test_borrar_personaje_borra_tambien_su_retrato(client, session, proy, dirs_tmp):
    f.personaje(session, proy.id)
    retrato = _archivo(dirs_tmp, "personajes", "ANA.png")
    r = client.delete(f"/api/proyectos/{proy.id}/personajes/ANA")
    assert r.json() == {"borrado": "ANA"} and not retrato.exists()
    assert client.delete(f"/api/proyectos/{proy.id}/personajes/ANA").status_code == 404


# --- voz por personaje ------------------------------------------------------

def _voz_banco(session, slug="ana-voz"):
    from backend.repositories import voces as voces_repo

    v = voces_repo.crear(session, slug, slug, "grave")
    v.estado = "lista"
    session.commit()
    return v


def test_asignar_y_quitar_la_voz_de_un_personaje(client, session, proy):
    _voz_banco(session)
    f.personaje(session, proy.id)

    assert client.put(f"/api/proyectos/{proy.id}/personajes/ANA/voz",
                      json={"voz": "ana-voz"}).json() == {"ok": True}
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].voz == "ana-voz"
    assert client.get(f"/api/proyectos/{proy.id}").json()["personajes"][0]["voz"] == "ana-voz"

    # Vacío lo deja sin voz propia: sus líneas las narra la voz del proyecto.
    client.put(f"/api/proyectos/{proy.id}/personajes/ANA/voz", json={"voz": ""})
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].voz == ""


def test_asignar_una_voz_que_no_existe_400_y_a_quien_no_existe_404(client, session, proy):
    f.personaje(session, proy.id)
    assert client.put(f"/api/proyectos/{proy.id}/personajes/ANA/voz",
                      json={"voz": "fantasma"}).status_code == 400
    assert client.put(f"/api/proyectos/{proy.id}/personajes/NADIE/voz",
                      json={"voz": ""}).status_code == 404
    assert client.put("/api/proyectos/99/personajes/ANA/voz",
                      json={"voz": ""}).status_code == 404


def test_crear_la_voz_de_un_personaje_desde_su_ficha(client, session, proy, jobs_encolados):
    """Su voz sale de donde ya sale su retrato: la ficha. Queda asignada en
    cuanto se encola, para que la UI diga de quién es mientras se sintetiza."""
    f.personaje(session, proy.id, nombre="Ana", ficha="a tall woman with red hair")

    r = client.post(f"/api/proyectos/{proy.id}/personajes/ANA/voz")

    body = r.json()
    assert body["slug"] == "ana" and jobs_encolados == [("crear_voz", body["voz_id"])]
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].voz == "ana"
    # La voz nace en el banco como cualquier otra, con la ficha dentro del
    # instruct de VoiceDesign y en los cuatro bloques que entiende.
    voz = client.get("/api/voces").json()[0]
    assert voz["slug"] == "ana" and "a tall woman with red hair" in voz["instruct"]
    assert "[PERFIL DE VOZ]" in voz["instruct"] and "[DINÁMICA Y RITMO]" in voz["instruct"]


def test_crear_la_voz_de_dos_personajes_con_el_mismo_nombre_no_choca(
    client, session, proy, jobs_encolados
):
    """Dos vídeos pueden tener cada uno su Ana: fallar con "ya existe una voz
    con nombre similar" obligaría a bautizarla justo cuando el nombre da igual."""
    f.personaje(session, proy.id, clave="ANA", nombre="Ana")
    f.personaje(session, proy.id, clave="ANA_2", nombre="Ana")

    primera = client.post(f"/api/proyectos/{proy.id}/personajes/ANA/voz").json()
    segunda = client.post(f"/api/proyectos/{proy.id}/personajes/ANA_2/voz").json()

    assert (primera["slug"], segunda["slug"]) == ("ana", "ana-2")


def test_crear_la_voz_de_un_personaje_sin_ficha_400(client, session, proy):
    f.personaje(session, proy.id, ficha="  ")
    assert client.post(f"/api/proyectos/{proy.id}/personajes/ANA/voz").status_code == 400
    assert client.post(f"/api/proyectos/{proy.id}/personajes/NADIE/voz").status_code == 404


def test_regenerar_el_casting_conserva_la_voz_elegida_a_mano(client, session, proy):
    """Elegirle voz es una decisión del usuario, no algo que el LLM reescriba:
    perderla al regenerar los prompts sería el mismo error que perder a los
    traídos del reparto propio, y encima solo se notaría al oír el vídeo."""
    _voz_banco(session)
    f.personaje(session, proy.id, voz="ana-voz")

    personajes_repo.reemplazar_todos(session, proy.id, [
        {"orden": 0, "clave": "ANA", "nombre": "Ana", "ficha": "otra ficha",
         "tipo": "persona", "seed": 3},
        {"orden": 1, "clave": "LUIS", "nombre": "Luis", "ficha": "f",
         "tipo": "persona", "seed": 4},
    ])
    session.commit()

    session.expire_all()
    voces = {x.clave: x.voz for x in personajes_repo.por_proyecto(session, proy.id)}
    assert voces == {"ANA": "ana-voz", "LUIS": ""}


def test_editar_casting_devuelve_cuantos_actualizo(client, session, proy):
    f.personaje(session, proy.id)
    r = client.put(f"/api/proyectos/{proy.id}/casting", json={"personajes": [
        {"clave": "ANA", "nombre": "Ana B", "ficha": "nueva"},
        {"clave": "NADIE", "nombre": "x", "ficha": "y"}]})
    assert r.json() == {"actualizados": 1}
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].nombre == "Ana B"


def test_editar_la_ficha_revisa_si_sigue_siendo_una_persona(client, session, proy):
    """El tipo no se manda por la API —lo decide el casting— pero reescribir la
    ficha con algo sin cara tiene que recolocarlo, o su retrato seguiría
    pidiendo rostro."""
    f.personaje(session, proy.id, tipo="persona")

    client.put(f"/api/proyectos/{proy.id}/casting", json={"personajes": [
        {"clave": "ANA", "nombre": "el mapa",
         "ficha": "a large worn tactical map on a table, no humans are visible"}]})

    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].tipo == "objeto"


def test_el_tipo_no_se_puede_forzar_desde_la_api(client, session, proy):
    f.personaje(session, proy.id, tipo="persona")
    # Un `tipo` en el cuerpo se ignora: el esquema no lo tiene.
    client.put(f"/api/proyectos/{proy.id}/casting", json={"personajes": [
        {"clave": "ANA", "nombre": "Ana", "ficha": "a woman with red hair",
         "tipo": "objeto"}]})
    session.expire_all()
    assert personajes_repo.por_proyecto(session, proy.id)[0].tipo == "persona"


def test_retrato_get_y_post_validan_la_clave(client, session, proy, dirs_tmp, jobs_encolados):
    assert client.get(f"/api/proyectos/{proy.id}/personajes/ANA/retrato").status_code == 404
    assert client.post(f"/api/proyectos/{proy.id}/personajes/ANA/retrato", json={}).status_code == 404
    assert jobs_encolados == []

    f.personaje(session, proy.id)
    assert client.get(f"/api/proyectos/{proy.id}/personajes/ANA/retrato").status_code == 404  # aún sin retrato
    _archivo(dirs_tmp, "personajes", "ANA.png", contenido=b"png")
    r = client.get(f"/api/proyectos/{proy.id}/personajes/ANA/retrato")
    assert r.status_code == 200 and r.content == b"png"
    r = client.post(f"/api/proyectos/{proy.id}/personajes/ANA/retrato", json={"nuevo_seed": False})
    assert r.status_code == 200
    assert jobs_encolados.params == [{"clave": "ANA", "nuevo_seed": False}]


def test_la_clave_del_retrato_no_puede_salirse_de_la_carpeta(client, session, proy):
    f.personaje(session, proy.id)
    r = client.get(f"/api/proyectos/{proy.id}/personajes/..%2F..%2Fsecreto/retrato")
    assert r.status_code == 404


# --- escenas ----------------------------------------------------------------

def test_editar_prompts_de_escenas_solo_toca_lo_enviado(client, session, proy):
    f.escenas(session, proy.id, n=2)
    escenas_repo.actualizar_prompts(session, proy.id, {1: {"prompt_movimiento": "pan left"}})
    session.commit()

    r = client.put(f"/api/proyectos/{proy.id}/escenas", json={"escenas": [
        {"orden": 1, "prompt": "nuevo prompt"}, {"orden": 7, "prompt": "no existe"}]})

    assert r.json() == {"actualizadas": 1}
    session.expire_all()
    e1 = escenas_repo.por_proyecto(session, proy.id)[0]
    assert (e1.prompt, e1.prompt_movimiento) == ("nuevo prompt", "pan left")


def test_editar_prompts_redetecta_los_personajes_de_la_escena(client, session, proy):
    f.escenas(session, proy.id, n=1)
    f.personaje(session, proy.id, ficha="a tall woman with red hair")
    client.put(f"/api/proyectos/{proy.id}/escenas", json={"escenas": [
        {"orden": 1, "prompt": "a tall woman with red hair walks"}]})
    session.expire_all()
    assert escenas_repo.por_proyecto(session, proy.id)[0].personajes == "ANA"


def test_editar_escenas_proyecto_inexistente_404(client):
    assert client.put("/api/proyectos/99/escenas", json={"escenas": []}).status_code == 404


def test_fijar_modos_de_escenas(client, session, proy):
    f.escenas(session, proy.id, n=2)
    r = client.put(f"/api/proyectos/{proy.id}/escenas/modos", json={"escenas": [
        {"orden": 2, "modo": "i2v"}, {"orden": 9, "modo": "kenburns"}]})
    assert r.json() == {"actualizadas": 1}
    session.expire_all()
    assert [e.modo for e in escenas_repo.por_proyecto(session, proy.id)] == ["", "i2v"]


# --- video ------------------------------------------------------------------

@pytest.mark.parametrize("modo,job", [
    ("estatico", "armar_estatico"), ("kenburns", "generar_upscale"),
    ("i2v", "generar_i2v"), ("mixto", "generar_clips_mixto")])
def test_generar_video_encola_el_job_del_modo(client, proy, jobs_encolados, modo, job):
    assert client.post(f"/api/proyectos/{proy.id}/video", json={"modo": modo}).status_code == 200
    assert jobs_encolados == [(job, proy.id)]


def test_generar_video_modo_invalido_400(client, proy, jobs_encolados):
    assert client.post(f"/api/proyectos/{proy.id}/video", json={"modo": "raro"}).status_code == 400
    assert jobs_encolados == []


def test_una_plantilla_de_motion_impone_su_modo(client, session, dirs_tmp, jobs_encolados):
    # El modo no se elige en motion: las escenas son fichas de composición y
    # cualquier otro modo se quedaría buscando imágenes que no existen.
    p = f.proyecto(session, slug="motion", plantilla="explica")
    assert client.post(f"/api/proyectos/{p.id}/video",
                       json={"modo": "kenburns"}).status_code == 200
    assert jobs_encolados == [("generar_clips_motion", p.id)]


def test_pedir_motion_a_una_plantilla_de_imagenes_es_400(client, proy, jobs_encolados):
    assert client.post(f"/api/proyectos/{proy.id}/video",
                       json={"modo": "motion"}).status_code == 400
    assert jobs_encolados == []


# --- versiones y borrado de video -------------------------------------------

def test_listar_ver_y_borrar_versiones(client, proy, dirs_tmp):
    v = _archivo(dirs_tmp, "versiones", "final_20260101.mp4", contenido=b"mp4")
    assert [x["nombre"] for x in client.get(f"/api/proyectos/{proy.id}/versiones").json()] == [v.name]
    assert client.get(f"/api/proyectos/{proy.id}/versiones/{v.name}").content == b"mp4"
    assert client.delete(f"/api/proyectos/{proy.id}/versiones/{v.name}").json() == {"borrada": v.name}
    assert not v.exists()
    assert client.delete(f"/api/proyectos/{proy.id}/versiones/{v.name}").status_code == 404


@pytest.mark.parametrize("nombre", ["final_x.txt", "otro.mp4", "final_..mp4", "..%2F..%2Ffinal_x.mp4"])
def test_versiones_con_nombre_invalido_no_tocan_nada(client, proy, dirs_tmp, nombre):
    # Un archivo con nombre "válido" fuera de versiones/: no debe poder alcanzarse.
    fuera = _archivo(dirs_tmp, "final_x.mp4")
    # %2F lo decodifica el servidor y la ruta ya no casa (404/405): también vale.
    assert client.get(f"/api/proyectos/{proy.id}/versiones/{nombre}").status_code in (400, 404)
    assert client.delete(f"/api/proyectos/{proy.id}/versiones/{nombre}").status_code in (404, 405)
    assert fuera.exists()


def test_versiones_de_proyecto_inexistente_404(client):
    assert client.get("/api/proyectos/99/versiones").status_code == 404


def test_borrar_video_con_y_sin_versiones(client, proy, dirs_tmp):
    final = _archivo(dirs_tmp, "final.mp4")
    ver = _archivo(dirs_tmp, "versiones", "final_1.mp4")
    assert client.delete(f"/api/proyectos/{proy.id}/video").json() == {"final": 1, "versiones": 0}
    assert not final.exists() and ver.exists()
    assert client.delete(f"/api/proyectos/{proy.id}/video?con_versiones=true").json() == {
        "final": 0, "versiones": 1}
    assert not ver.exists()


def test_borrar_video_de_proyecto_inexistente_404(client):
    assert client.delete("/api/proyectos/99/video").status_code == 404


# --- publicación ------------------------------------------------------------

def test_marcar_publicado_apunta_fecha_enlace_y_nota(client, proy):
    r = client.put(f"/api/proyectos/{proy.id}/publicacion", json={
        "fecha": "2026-10-20", "url": "abc123", "nota": "Canal nuevo"})
    assert r.json() == {"fecha": "2026-10-20", "url": "abc123", "nota": "Canal nuevo"}
    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["publicacion"] == {"fecha": "2026-10-20", "url": "abc123", "nota": "Canal nuevo"}
    # Y el listado lo dice sin tener que abrir el proyecto.
    assert client.get("/api/proyectos").json()[0]["publicado_en"] == "2026-10-20"


def test_sin_publicar_el_detalle_lo_dice(client, proy):
    assert client.get(f"/api/proyectos/{proy.id}").json()["publicacion"] is None


@pytest.mark.parametrize("fecha", ["", "ayer", "20/10/2026", "2026-13-45"])
def test_una_fecha_que_no_es_fecha_se_cambia_por_hoy(client, proy, fecha):
    """La teclea quien marca el vídeo: una fecha inventada se quedaría
    guardada y se enseñaría igual."""
    from datetime import datetime

    r = client.put(f"/api/proyectos/{proy.id}/publicacion", json={"fecha": fecha})
    assert r.json()["fecha"] == datetime.now().strftime("%Y-%m-%d")


def test_volver_a_marcarlo_corrige_los_datos(client, proy):
    client.put(f"/api/proyectos/{proy.id}/publicacion", json={
        "fecha": "2026-10-20", "url": "abc123", "nota": "n"})
    r = client.put(f"/api/proyectos/{proy.id}/publicacion", json={
        "fecha": "2026-10-21", "url": "https://youtu.be/otro", "nota": ""})
    assert r.json() == {"fecha": "2026-10-21", "url": "https://youtu.be/otro", "nota": ""}


def test_quitar_la_marca_no_toca_el_disco(client, proy, dirs_tmp):
    final = _archivo(dirs_tmp, "final.mp4")
    client.put(f"/api/proyectos/{proy.id}/publicacion", json={"fecha": "2026-10-20"})
    assert client.delete(f"/api/proyectos/{proy.id}/publicacion").json() == {"publicado": False}
    assert client.get(f"/api/proyectos/{proy.id}").json()["publicacion"] is None
    assert final.exists()


def test_publicacion_de_proyecto_inexistente_404(client):
    assert client.put("/api/proyectos/99/publicacion", json={}).status_code == 404
    assert client.delete("/api/proyectos/99/publicacion").status_code == 404


# --- liberar espacio --------------------------------------------------------

def test_el_detalle_cuenta_lo_que_ocupa_y_lo_que_se_puede_tirar(client, proy, dirs_tmp):
    _archivo(dirs_tmp, "final.mp4", contenido=b"x" * 300)
    _archivo(dirs_tmp, "imagenes", "01.png", contenido=b"x" * 100)
    _archivo(dirs_tmp, "upscale", "01.png", contenido=b"x" * 500)

    disco = client.get(f"/api/proyectos/{proy.id}").json()["disco"]

    assert disco["total_mb"] == round(900 / 1e6, 1)
    # Se puede tirar todo menos el vídeo final.
    assert disco["liberable_mb"] == round(600 / 1e6, 1)


def test_liberar_deja_solo_el_video_final(client, proy, dirs_tmp):
    client.put(f"/api/proyectos/{proy.id}/publicacion", json={"fecha": "2026-10-20"})
    final = _archivo(dirs_tmp, "final.mp4")
    tirables = [
        _archivo(dirs_tmp, "voz.mp3"),
        _archivo(dirs_tmp, "voz.wav"),
        _archivo(dirs_tmp, "voz_raw.wav"),
        _archivo(dirs_tmp, "subtitulos.srt"),
        _archivo(dirs_tmp, "palabras.json"),
        _archivo(dirs_tmp, "imagenes", "01.png"),
        _archivo(dirs_tmp, "upscale", "01.png"),
        _archivo(dirs_tmp, "clips", "01.mp4"),
        _archivo(dirs_tmp, "subs", "000.png"),
        _archivo(dirs_tmp, "armado", "x.mp4"),
        _archivo(dirs_tmp, "versiones", "final_1.mp4"),
        _archivo(dirs_tmp, "personajes", "ana.png"),
    ]

    r = client.post(f"/api/proyectos/{proy.id}/liberar")

    assert r.json()["archivos"] == len(tirables)
    assert not any(x.exists() for x in tirables)
    assert final.exists()
    assert [x.name for x in (dirs_tmp["proyectos"] / "demo").iterdir()] == ["final.mp4"]


def test_liberado_el_proyecto_lo_dice_en_vez_de_parecer_a_medio_hacer(client, proy, dirs_tmp):
    """Sin esto la ficha enseñaría un vídeo publicado como si le faltaran la
    voz y las imágenes, que es lo que se tiró a propósito."""
    client.put(f"/api/proyectos/{proy.id}/publicacion", json={"fecha": "2026-10-20"})
    _archivo(dirs_tmp, "final.mp4")
    _archivo(dirs_tmp, "imagenes", "01.png")
    assert client.get(f"/api/proyectos/{proy.id}").json()["liberado"] is False

    client.post(f"/api/proyectos/{proy.id}/liberar")

    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["liberado"] is True
    # El vídeo sigue ahí y el enlace también; lo que no está es el material.
    assert d["video_disponible"] and d["publicacion"] is not None
    assert d["voz_disponible"] is False and d["disco"]["liberable_mb"] == 0


def test_volver_a_generar_las_imagenes_deja_de_contar_como_liberado(client, proy, dirs_tmp):
    """La marca se mira en el disco justo para esto: si vuelve a haber material,
    deja de ser verdad sola."""
    client.put(f"/api/proyectos/{proy.id}/publicacion", json={"fecha": "2026-10-20"})
    _archivo(dirs_tmp, "final.mp4")
    client.post(f"/api/proyectos/{proy.id}/liberar")

    _archivo(dirs_tmp, "imagenes", "01.png")

    assert client.get(f"/api/proyectos/{proy.id}").json()["liberado"] is False


def test_sin_publicar_nunca_cuenta_como_liberado(client, proy, dirs_tmp):
    _archivo(dirs_tmp, "final.mp4")
    assert client.get(f"/api/proyectos/{proy.id}").json()["liberado"] is False


def test_liberar_sin_publicar_409(client, proy, dirs_tmp):
    """Hasta que el vídeo está arriba, esto es el material que rehace el
    montaje; para borrarlo están los botones de siempre."""
    up = _archivo(dirs_tmp, "upscale", "01.png")
    assert client.post(f"/api/proyectos/{proy.id}/liberar").status_code == 409
    assert up.exists()


def test_liberar_con_trabajo_en_curso_409(client, session, proy, dirs_tmp):
    client.put(f"/api/proyectos/{proy.id}/publicacion", json={"fecha": "2026-10-20"})
    up = _archivo(dirs_tmp, "upscale", "01.png")
    session.add(Job(tipo="generar_clips", ref_id=proy.id, estado="pendiente"))
    session.commit()
    assert client.post(f"/api/proyectos/{proy.id}/liberar").status_code == 409
    assert up.exists()


def test_liberar_dos_veces_no_falla(client, proy, dirs_tmp):
    client.put(f"/api/proyectos/{proy.id}/publicacion", json={"fecha": "2026-10-20"})
    _archivo(dirs_tmp, "final.mp4")
    _archivo(dirs_tmp, "upscale", "01.png")
    assert client.post(f"/api/proyectos/{proy.id}/liberar").json()["archivos"] == 1
    assert client.post(f"/api/proyectos/{proy.id}/liberar").json()["archivos"] == 0


def test_liberar_de_proyecto_inexistente_404(client):
    assert client.post("/api/proyectos/99/liberar").status_code == 404


# --- borrar proyecto --------------------------------------------------------

def test_borrar_proyecto_limpia_filas_y_carpeta(client, session, proy, dirs_tmp):
    pid = proy.id
    f.escenas(session, pid)
    f.personaje(session, pid)
    _archivo(dirs_tmp, "final.mp4")
    _archivo(dirs_tmp, "imagenes", "01.png")

    r = client.delete(f"/api/proyectos/{pid}")

    assert r.json() == {"slug": "demo", "archivos": 2}
    assert not (dirs_tmp["proyectos"] / "demo").exists()
    session.expire_all()
    assert proyectos_repo.obtener(session, pid) is None
    assert escenas_repo.por_proyecto(session, pid) == []
    assert personajes_repo.por_proyecto(session, pid) == []


def test_borrar_proyecto_con_trabajo_en_curso_409(client, session, proy):
    session.add(Job(tipo="generar_voz", ref_id=proy.id, estado="pendiente"))
    session.commit()
    assert client.delete(f"/api/proyectos/{proy.id}").status_code == 409
    session.expire_all()
    assert proyectos_repo.obtener(session, proy.id) is not None


def test_borrar_proyecto_inexistente_404(client):
    assert client.delete("/api/proyectos/99").status_code == 404


# --- archivos servidos ------------------------------------------------------

@pytest.mark.parametrize("ruta,partes,tipo", [
    ("audio", ("voz.mp3",), "audio/mpeg"),
    ("imagenes/3", ("imagenes", "03.png"), "image/png"),
    ("clips/3", ("clips", "03.mp4"), "video/mp4"),
    ("video", ("final.mp4",), "video/mp4"),
])
def test_servir_archivos_404_hasta_que_existen(client, proy, dirs_tmp, ruta, partes, tipo):
    assert client.get(f"/api/proyectos/{proy.id}/{ruta}").status_code == 404
    _archivo(dirs_tmp, *partes, contenido=b"datos")
    r = client.get(f"/api/proyectos/{proy.id}/{ruta}")
    assert r.status_code == 200 and r.content == b"datos"
    assert r.headers["content-type"].startswith(tipo)


def test_servir_archivo_de_proyecto_inexistente_404(client):
    assert client.get("/api/proyectos/99/video").status_code == 404


# --- música del proyecto ----------------------------------------------------

def _pista(session, idea="banda sonora", estado="generada"):
    from backend.repositories import musica as musica_repo

    m = musica_repo.crear(session, "instrumental", idea, "tags", "[Intro]",
                          30, 90, "E minor", "4", "en")
    m.estado = estado
    session.commit()
    return m.id


def test_detalle_sin_musica(client, proy):
    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["musica"] is None and d["musica_mezclar"] is False


def test_generar_musica_encola_el_brief(client, proy, jobs_encolados):
    r = client.post(f"/api/proyectos/{proy.id}/musica")
    assert r.status_code == 200 and r.json()["job_id"]
    assert ("generar_musica_proyecto", proy.id) in jobs_encolados


def test_fijar_una_pista_de_la_biblioteca_y_activar_la_mezcla(client, session, proy, dirs_tmp):
    mid = _pista(session)

    assert client.put(f"/api/proyectos/{proy.id}/musica",
                      json={"musica_id": mid, "mezclar": True}).status_code == 200

    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["musica"]["id"] == mid and d["musica"]["idea"] == "banda sonora"
    assert d["musica"]["tiene_audio"] is False  # la fila existe, el audio no
    assert d["musica_mezclar"] is True


def test_soltar_la_pista_apaga_la_mezcla(client, session, proy, dirs_tmp):
    mid = _pista(session)
    client.put(f"/api/proyectos/{proy.id}/musica", json={"musica_id": mid, "mezclar": True})

    client.put(f"/api/proyectos/{proy.id}/musica", json={"musica_id": None, "mezclar": True})

    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["musica"] is None and d["musica_mezclar"] is False


def test_fijar_una_pista_que_no_existe_404(client, proy):
    r = client.put(f"/api/proyectos/{proy.id}/musica", json={"musica_id": 99, "mezclar": True})
    assert r.status_code == 404


def test_borrar_la_pista_desengancha_el_proyecto(client, session, proy, dirs_tmp):
    """Si no, el proyecto quedaría apuntando a una pista fantasma y el armado
    con mezcla fallaría."""
    mid = _pista(session)
    client.put(f"/api/proyectos/{proy.id}/musica", json={"musica_id": mid, "mezclar": True})

    assert client.delete(f"/api/musica/{mid}").json()["proyectos_desvinculados"] == 1

    d = client.get(f"/api/proyectos/{proy.id}").json()
    assert d["musica"] is None and d["musica_mezclar"] is False
