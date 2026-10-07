import json

import pytest

from backend.models import Voz
from backend.repositories import ajustes as ajustes_repo
from backend.repositories import guiones as guiones_repo
from backend.repositories import jobs as jobs_repo
from backend.repositories import personajes as personajes_repo
from backend.repositories import plantillas as plantillas_repo
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import temas as temas_repo
from tests import factories as f


# --- guiones ----------------------------------------------------------------

@pytest.mark.parametrize("guion,esperado", [
    ({"gancho": "G", "frases": ["a", "b"], "cta": "C"}, "G a b C"),
    ({"gancho": "G", "narracion": " cuerpo ", "cta": "C"}, "G cuerpo C"),
    ({"gancho": "G", "narracion": "n", "frases": ["ignorada"], "cta": "C"}, "G n C"),
    ({"gancho": "G", "narracion": "   ", "frases": ["f"], "cta": ""}, "G f"),
    ({}, ""),
    ({"frases": ["", "  ", "x"]}, "x"),
])
def test_texto_narrado(guion, esperado):
    assert guiones_repo.texto_narrado(guion) == esperado


def test_guiones_se_versionan(session):
    p = f.proyecto(session)
    assert guiones_repo.ultimo(session, p.id) is None
    guiones_repo.crear(session, p.id, {"gancho": "á"})
    guiones_repo.crear(session, p.id, {"gancho": "b"})
    session.commit()
    ultimo = guiones_repo.ultimo(session, p.id)
    assert ultimo.version == 2 and json.loads(ultimo.contenido) == {"gancho": "b"}
    assert "á" in guiones_repo.crear(session, p.id, {"gancho": "á"}).contenido  # sin escapar


# --- personajes -------------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("ana", "ANA"),
    ("  el escritor  raro ", "EL_ESCRITOR_RARO"),
    ("a--b!!c", "ABC"),
    ("__x__", "X"),
    ("a___b", "A_B"),
    ("", ""),
    ("!!!", ""),
])
def test_normalizar_clave(entrada, esperado):
    assert personajes_repo.normalizar_clave(entrada) == esperado


def test_personajes_se_ordenan_en_orden_de_alta(session):
    p = f.proyecto(session)
    for clave in ("B", "A", "C"):
        f.personaje(session, p.id, clave=clave, ficha="")
    assert [x.clave for x in personajes_repo.por_proyecto(session, p.id)] == ["B", "A", "C"]
    assert personajes_repo.fichas(session, p.id) == {}  # sin ficha, fuera del casting


def test_actualizar_personajes_ignora_claves_desconocidas(session):
    p = f.proyecto(session)
    f.personaje(session, p.id)
    n = personajes_repo.actualizar(session, p.id, {"ANA": {"nombre": "N"}, "X": {"nombre": "?"}})
    assert n == 1
    assert personajes_repo.por_proyecto(session, p.id)[0].ficha == "a tall woman with red hair"


def test_borrar_personaje_devuelve_filas(session):
    p = f.proyecto(session)
    f.personaje(session, p.id)
    assert personajes_repo.borrar(session, p.id, "ANA") == 1
    assert personajes_repo.borrar(session, p.id, "ANA") == 0


# --- proyectos --------------------------------------------------------------

def test_slug_existe_y_por_idea(session):
    p = f.proyecto(session, slug="uno")
    assert proyectos_repo.slug_existe(session, "uno")
    assert not proyectos_repo.slug_existe(session, "otro")
    assert proyectos_repo.por_idea(session, p.idea_id).id == p.id
    assert proyectos_repo.por_idea(session, 999) is None


def test_listar_proyectos_del_mas_nuevo_al_mas_viejo(session):
    a = f.proyecto(session, slug="a")
    b = f.proyecto(session, slug="b")
    assert [p.id for p in proyectos_repo.listar(session)] == [b.id, a.id]


def test_desvincular_voz(session):
    a, b = f.proyecto(session, slug="a"), f.proyecto(session, slug="b")
    a.voz = b.voz = "ana"
    session.commit()
    assert proyectos_repo.desvincular_voz(session, "ana") == 2
    assert proyectos_repo.desvincular_voz(session, "ana") == 0


def test_borrar_proyecto_se_lleva_a_sus_dependientes(session):
    from backend.models import Escena, Guion, Job, Personaje

    p = f.proyecto(session)
    pid = p.id
    f.escenas(session, pid)
    f.personaje(session, pid)
    guiones_repo.crear(session, pid, {})
    otro = f.proyecto(session, slug="otro")
    from backend.models import Job as J
    session.add_all([J(tipo="generar_voz", ref_id=pid, estado="ok"),
                     J(tipo="generar_voz", ref_id=otro.id, estado="ok")])
    session.commit()

    proyectos_repo.borrar(session, pid)
    session.commit()

    for modelo in (Escena, Personaje, Guion):
        assert session.query(modelo).filter(modelo.proyecto_id == pid).count() == 0
    # Los jobs del otro proyecto (mismo tipo, otro ref_id) no se tocan.
    assert [j.ref_id for j in session.query(Job).all()] == [otro.id]
    assert proyectos_repo.obtener(session, otro.id) is not None


# --- temas ------------------------------------------------------------------

def test_borrar_tema_borra_sus_ideas(session):
    t = f.tema(session)
    f.idea(session, t.id)
    temas_repo.borrar(session, t.id)
    session.commit()
    from backend.models import Idea
    assert session.query(Idea).count() == 0


# --- ajustes ----------------------------------------------------------------

def test_ajustes_leer_escribir(session):
    assert ajustes_repo.leer(session, "k") is None
    ajustes_repo.escribir(session, "k", "1")
    ajustes_repo.escribir(session, "k", "2")
    session.commit()
    assert ajustes_repo.leer(session, "k") == "2"


# --- jobs -------------------------------------------------------------------

def test_jobs_activos_y_ciclo_de_vida(session):
    j = jobs_repo.crear(session, "generar_voz", 1)
    session.commit()
    assert j.estado == "pendiente" and [x.id for x in jobs_repo.activos(session)] == [j.id]
    jobs_repo.marcar_corriendo(session, j)
    assert j.estado == "corriendo"
    jobs_repo.finalizar(session, j, "ok", "log")
    session.commit()
    assert jobs_repo.activos(session) == []
    assert j.finished_at is not None and j.log == "log"


def test_activos_de_proyecto_filtra_por_tipo_y_ref(session):
    jobs_repo.crear(session, "generar_voz", 1)
    jobs_repo.crear(session, "generar_imagenes", 1)
    jobs_repo.crear(session, "generar_voz", 2)
    session.commit()
    assert jobs_repo.activos_de_proyecto(session, 1, ["generar_voz"]) == 1
    assert jobs_repo.activos_de_proyecto(session, 1, []) == 0
    assert jobs_repo.tipo_activo_de_proyecto(session, 1, ["generar_voz", "generar_imagenes"]) == "generar_voz"
    assert jobs_repo.tipo_activo_de_proyecto(session, 3, ["generar_voz"]) is None


def test_escenas_en_cola_distingue_imagen_de_clip(session):
    jobs_repo.crear(session, "regenerar_imagen", 1, json.dumps({"orden": 2}))
    jobs_repo.crear(session, "regenerar_clip", 1, json.dumps({"orden": 3}))
    jobs_repo.crear(session, "regenerar_clip", 9, json.dumps({"orden": 4}))  # otro proyecto
    session.commit()
    assert jobs_repo.escenas_en_cola(session, 1) == {2: "imagen", 3: "clip"}


# --- plantillas -------------------------------------------------------------

def test_plantilla_inexistente():
    with pytest.raises(plantillas_repo.PlantillaNoEncontrada):
        plantillas_repo.cargar("no_existe")


def test_plantillas_listadas_y_ordenadas():
    nombres = plantillas_repo.listar()
    assert nombres == sorted(nombres) and "curiosidades" in nombres


def test_voces_ruta_ref_y_borrado(session, dirs_tmp):
    from backend.repositories import voces as voces_repo

    v = voces_repo.crear(session, "ana", "Ana", "x")
    session.commit()
    assert voces_repo.por_slug(session, "ana").id == v.id
    assert voces_repo.ruta_ref("ana") == dirs_tmp["voces"] / "ana" / "ref.wav"
    voces_repo.borrar(session, v)
    session.commit()
    assert voces_repo.listar(session) == []
