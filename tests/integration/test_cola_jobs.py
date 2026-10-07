"""La cola de verdad (`queue.encolar` + `_procesar`), con handlers de mentira."""
import pytest

from backend.repositories import jobs as jobs_repo
from backend.workers import queue

pytestmark = pytest.mark.integration


@pytest.fixture
def cola(engine, monkeypatch):
    """Cola real sobre la BD temporal, sin llama-server y con handlers sustituibles."""
    from backend.services import llm_runtime

    llamadas = []
    monkeypatch.setattr(llm_runtime, "liberar", lambda motivo: llamadas.append(("liberar", motivo)))
    monkeypatch.setattr(queue, "HANDLERS", dict(queue.HANDLERS))
    while not queue._cola.empty():
        queue._cola.get_nowait()
    yield llamadas
    while not queue._cola.empty():
        queue._cola.get_nowait()


def _estado(job_id):
    from backend.db import get_session

    with get_session() as s:
        j = jobs_repo.obtener(s, job_id)
        return j.estado, j.log


def test_encolar_tipo_desconocido(cola):
    with pytest.raises(ValueError, match="desconocido"):
        queue.encolar("no_existe", 1)


def test_job_ok_pasa_params_como_kwargs_y_guarda_log(cola):
    recibido = {}
    queue.HANDLERS["generar_clips"] = lambda ref, **kw: recibido.update(ref=ref, **kw) or "hecho"
    queue.HANDLERS["armar_video"] = lambda ref, **kw: "armado"
    jid = queue.encolar("generar_clips", 7, orden=3)

    queue._procesar(queue._cola.get())

    assert recibido == {"ref": 7, "orden": 3}
    assert _estado(jid) == ("ok", "hecho")
    # Etapa de GPU: se descarga el LLM antes de empezar.
    assert cola == [("liberar", "empieza generar_clips")]


def test_job_con_excepcion_queda_en_error_y_no_encadena(cola):
    def roto(ref):
        raise RuntimeError("boom")

    queue.HANDLERS["generar_clips"] = roto
    jid = queue.encolar("generar_clips", 1)

    queue._procesar(queue._cola.get())

    estado, log = _estado(jid)
    assert estado == "error" and "boom" in log
    assert queue._cola.empty()


def test_job_ok_encadena_el_siguiente(cola):
    queue.HANDLERS["generar_clips"] = lambda ref: "ok"
    jid = queue.encolar("generar_clips", 5)

    queue._procesar(queue._cola.get())

    siguiente = queue._cola.get_nowait()
    assert siguiente != jid
    from backend.db import get_session

    with get_session() as s:
        j = jobs_repo.obtener(s, siguiente)
        assert (j.tipo, j.ref_id) == ("armar_video", 5)


def test_job_de_llm_usa_en_uso_y_no_libera(cola, monkeypatch):
    from backend.services import llm_runtime
    import contextlib

    entradas = []

    @contextlib.contextmanager
    def en_uso():
        entradas.append("entra")
        yield

    monkeypatch.setattr(llm_runtime, "en_uso", en_uso)
    queue.HANDLERS["generar_ideas"] = lambda ref: "ideas"
    jid = queue.encolar("generar_ideas", 1)

    queue._procesar(queue._cola.get())

    assert entradas == ["entra"] and cola == []
    assert _estado(jid) == ("ok", "ideas")
