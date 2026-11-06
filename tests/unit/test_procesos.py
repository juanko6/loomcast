"""Ningún proceso externo puede dejar un job colgado: todos pasan por `procesos.ejecutar`."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from backend import procesos
from backend.clients import rife
from backend.services.pipeline import _ffmpeg, _masterizar
from tests import fakes


def test_ejecutar_devuelve_el_resultado():
    r = procesos.ejecutar([sys.executable, "-c", "print('hola')"], timeout=10,
                          capture_output=True, text=True)
    assert r.stdout.strip() == "hola"


def test_ejecutar_respeta_check():
    with pytest.raises(subprocess.CalledProcessError):
        procesos.ejecutar([sys.executable, "-c", "raise SystemExit(3)"], timeout=10, check=True)


def test_ejecutar_mata_el_proceso_que_se_pasa_y_nombra_la_tarea():
    with pytest.raises(procesos.ProcesoTimeout, match=r"ffmpeg \(prueba\) no terminó en 1 s"):
        procesos.ejecutar([sys.executable, "-c", "import time; time.sleep(30)"],
                          timeout=1, que="ffmpeg (prueba)")


def test_el_timeout_sin_nombre_usa_el_ejecutable():
    with pytest.raises(procesos.ProcesoTimeout, match="no terminó"):
        procesos.ejecutar([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)


def test_terminar_actual_corta_el_proceso_en_marcha(monkeypatch):
    """Parar un job tiene que alcanzar al ffmpeg (o ESRGAN, o RIFE) que corre.

    El proceso se registra al lanzarlo, así que el hilo HTTP puede pedirle que
    termine mientras el de la cola sigue bloqueado esperándolo.
    """
    import threading

    arrancado = threading.Event()

    def mirando():
        while not procesos._vivos:
            pass
        arrancado.set()
        procesos.terminar_actual()

    threading.Thread(target=mirando, daemon=True).start()
    with pytest.raises(procesos.ProcesoParado, match=r"ffmpeg \(prueba\) se paró"):
        procesos.ejecutar([sys.executable, "-c", "import time; time.sleep(30)"],
                          timeout=30, que="ffmpeg (prueba)")
    assert arrancado.is_set()
    # Y no queda rastro: ni procesos vivos ni pids marcados de la vez anterior.
    assert not procesos._vivos and not procesos._parados


def test_sin_procesos_en_marcha_terminar_actual_no_hace_nada():
    assert procesos.terminar_actual() == 0


@pytest.fixture
def todo_se_cuelga(monkeypatch):
    """Cualquier proceso externo excede su tope; guarda los timeouts pedidos."""
    pedidos = []

    def colgado(cmd, **kw):
        pedidos.append(kw.get("timeout"))
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 0)

    monkeypatch.setattr(subprocess, "Popen", fakes.popen_falso(colgado))
    return pedidos


def test_ffprobe_colgado_da_duracion_cero(todo_se_cuelga, tmp_path):
    assert _ffmpeg.duracion(tmp_path / "x.mp4") == 0.0
    assert todo_se_cuelga == [procesos.SONDEO_S]


def test_masterizado_colgado_sube_como_masterizar_error(todo_se_cuelga, tmp_path):
    # Para que la pista se entregue sin masterizar en vez de colgar el job.
    with pytest.raises(_masterizar.MasterizarError, match="no terminó"):
        _masterizar.masterizar(tmp_path / "a.flac", tmp_path / "b.flac")
    assert todo_se_cuelga == [procesos.MASTERIZADO_S]


def test_rife_colgado_sube_como_rife_error(todo_se_cuelga, tmp_path, monkeypatch):
    monkeypatch.setattr(rife, "ROOT", tmp_path)
    monkeypatch.setattr(rife, "RIFE_BIN", "rife/bin")
    monkeypatch.setattr(rife, "RIFE_MODELO", "m")
    (tmp_path / "rife" / "m").mkdir(parents=True)
    (tmp_path / "rife" / "bin").write_text("")
    with pytest.raises(rife.RifeError, match="ffmpeg .*no terminó"):
        rife.interpolar(tmp_path / "a.mp4", tmp_path / "b.mp4", 12, 60)
    assert todo_se_cuelga == [procesos.CORTO_S]


def test_voz_y_recorte_de_referencia_tienen_tope(todo_se_cuelga, session, dirs_tmp, fake_tts):
    import soundfile as sf

    from backend.repositories import guiones as guiones_repo
    from backend.repositories import voces as voces_repo
    from backend.services.pipeline import crear_voz, voz
    from tests import factories as f

    p = f.proyecto(session)
    guiones_repo.crear(session, p.id, {"gancho": "G", "frases": ["f"], "cta": "C"})
    session.commit()
    with pytest.raises(procesos.ProcesoTimeout, match="atempo"):
        voz.generar_voz(p.id, modo="design")

    v = voces_repo.crear(session, "clon", "clon", "x")
    session.commit()
    base = dirs_tmp["voces"] / "clon"
    base.mkdir()
    sf.write(base / "origen.wav", [0.1] * 24000, 24000)
    with pytest.raises(procesos.ProcesoTimeout, match="recorte"):
        crear_voz.clonar_voz(v.id)
    session.expire_all()
    assert voces_repo.obtener(session, v.id).estado == "error"
    assert todo_se_cuelga == [procesos.CORTO_S, procesos.CORTO_S]


def test_nadie_llama_a_subprocess_run_sin_pasar_por_procesos():
    """Guarda contra regresiones: un `subprocess.run(` suelto vuelve a abrir el cuelgue."""
    raiz = Path(__file__).resolve().parents[2] / "backend"
    sueltos = []
    for f in raiz.rglob("*.py"):
        if f.name == "procesos.py":
            continue
        for n, linea in enumerate(f.read_text().splitlines(), 1):
            if re.search(r"subprocess\.run\(", linea):
                sueltos.append(f"{f.relative_to(raiz.parent)}:{n}")
    # Las permitidas son consultas al sistema para saber qué hay vivo o cuánta
    # memoria queda, todas con su propio timeout=5: `ps` para el instante de
    # arranque de un pgid y `lsof` para quién sirve un puerto (llm_runtime), y
    # `vm_stat` para el contador de swap (memoria). No son trabajo del
    # pipeline: no hay nada que cancelar en ellas, no leen stdin —que es de
    # donde venía el cuelgue— y registrarlas en la parada solo haría ruido.
    assert {s.split(":")[0] for s in sueltos} == {
        "backend/services/llm_runtime.py",
        "backend/memoria.py",
    }
    assert len(sueltos) == 3, sueltos


def test_ejecutar_no_le_deja_la_terminal_al_proceso(monkeypatch):
    """ffmpeg lee stdin para sus teclas interactivas. Si hereda la terminal
    estando en un grupo en segundo plano (lo que pasa al arrancar con
    scripts/run-loomcast.sh), el kernel le manda SIGTTIN y suspende el backend
    entero: se queda congelado hasta que algo le mande SIGCONT."""
    visto = {}

    def falso_run(cmd, **kw):
        visto.update(kw)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "Popen", fakes.popen_falso(falso_run))
    procesos.ejecutar(["ffmpeg", "-i", "x"], timeout=10)

    assert visto["stdin"] is subprocess.DEVNULL
