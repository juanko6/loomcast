import pytest

from backend.models import Job, Voz
from backend.repositories import proyectos as proyectos_repo
from backend.repositories import voces as voces_repo
from tests import factories as f

pytestmark = pytest.mark.integration


def _clonar(client, nombre="Mi Voz", archivo=("voz.wav", b"RIFF"), **extra):
    return client.post("/api/voces/clonar", data={"nombre": nombre, **extra},
                       files={"audio": (archivo[0], archivo[1], "audio/wav")})


def test_listar_vacio(client):
    assert client.get("/api/voces").json() == []


def test_crear_voz_encola_el_diseno(client, dirs_tmp, jobs_encolados):
    r = client.post("/api/voces", json={"nombre": "Ñandú Épico", "instruct": " grave "})
    body = r.json()
    assert r.status_code == 200 and body["slug"] == "nandu-epico"
    assert jobs_encolados == [("crear_voz", body["voz_id"])]
    voz = client.get("/api/voces").json()[0]
    assert (voz["nombre"], voz["instruct"], voz["disponible"]) == ("Ñandú Épico", "grave", False)


def test_crear_voz_con_nombre_similar_409(client, dirs_tmp):
    client.post("/api/voces", json={"nombre": "Ana", "instruct": "x"})
    assert client.post("/api/voces", json={"nombre": "ANA!", "instruct": "x"}).status_code == 409


def test_crear_voz_sin_campos_422(client):
    assert client.post("/api/voces", json={"nombre": "solo"}).status_code == 422


def test_crear_voz_con_nombre_sin_caracteres_validos_usa_slug_generico(client, dirs_tmp):
    assert client.post("/api/voces", json={"nombre": "¿¿??", "instruct": "x"}).json()["slug"] == "voz"


def test_clonar_guarda_el_origen_y_encola_con_recorte(client, dirs_tmp, jobs_encolados):
    r = _clonar(client, descripcion="  cálida ", inicio="1.5", fin="9")
    assert r.status_code == 200
    assert (dirs_tmp["voces"] / "mi-voz" / "origen.wav").read_bytes() == b"RIFF"
    assert jobs_encolados == [("clonar_voz", r.json()["voz_id"])]
    assert jobs_encolados.params == [{"inicio": 1.5, "fin": 9.0}]
    assert client.get("/api/voces").json()[0]["instruct"] == "cálida"


def test_clonar_sin_recorte_ni_descripcion(client, dirs_tmp, jobs_encolados):
    _clonar(client)
    assert jobs_encolados.params == [{"inicio": 0.0, "fin": None}]
    assert client.get("/api/voces").json()[0]["instruct"] == "Clonada desde un audio de referencia."


@pytest.mark.parametrize("nombre,archivo,mensaje", [
    ("   ", ("a.wav", b"x"), "nombre"),
    ("v", ("a.txt", b"x"), "Formato"),
    ("v", ("sin_extension", b"x"), "desconocido"),
    ("v", ("a.wav", b""), "vacío"),
])
def test_clonar_con_entrada_invalida_400(client, dirs_tmp, jobs_encolados, nombre, archivo, mensaje):
    r = _clonar(client, nombre=nombre, archivo=archivo)
    assert r.status_code == 400 and mensaje in r.json()["detail"]
    assert jobs_encolados == []


def test_clonar_audio_demasiado_grande_400(client, dirs_tmp, monkeypatch):
    from backend.services import voces

    monkeypatch.setattr(voces, "MAX_AUDIO_BYTES", 3)
    assert _clonar(client, archivo=("a.wav", b"1234")).status_code == 400


def test_clonar_con_slug_repetido_409_y_sin_audio_422(client, dirs_tmp):
    _clonar(client)
    assert _clonar(client).status_code == 409
    assert client.post("/api/voces/clonar", data={"nombre": "x"}).status_code == 422


def test_borrar_voz_desvincula_proyectos_y_borra_carpeta(client, session, dirs_tmp):
    session.add(Voz(slug="ana", nombre="Ana", instruct="x"))
    p = f.proyecto(session)
    p.voz = "ana"
    session.commit()
    pid = p.id
    carpeta = dirs_tmp["voces"] / "ana"
    carpeta.mkdir()
    (carpeta / "ref.wav").write_bytes(b"w")

    r = client.delete("/api/voces/ana")

    assert r.json() == {"slug": "ana", "proyectos_desvinculados": 1}
    assert not carpeta.exists()
    session.expire_all()
    assert proyectos_repo.obtener(session, pid).voz is None
    assert voces_repo.por_slug(session, "ana") is None


def test_borrar_voz_inexistente_404(client):
    assert client.delete("/api/voces/nadie").status_code == 404


def test_borrar_voz_mientras_se_genera_409(client, session, dirs_tmp):
    v = Voz(slug="ana", nombre="Ana", instruct="x")
    session.add(v)
    session.commit()
    session.add(Job(tipo="crear_voz", ref_id=v.id, estado="corriendo"))
    session.commit()
    assert client.delete("/api/voces/ana").status_code == 409
    assert voces_repo.por_slug(session, "ana") is not None


def test_audio_de_voz(client, session, dirs_tmp):
    assert client.get("/api/voces/ana/audio").status_code == 404
    (dirs_tmp["voces"] / "ana").mkdir()
    (dirs_tmp["voces"] / "ana" / "ref.wav").write_bytes(b"wav")
    r = client.get("/api/voces/ana/audio")
    assert r.status_code == 200 and r.content == b"wav"
    session.add(Voz(slug="ana", nombre="Ana", instruct="x"))
    session.commit()
    assert client.get("/api/voces").json()[0]["disponible"] is True
