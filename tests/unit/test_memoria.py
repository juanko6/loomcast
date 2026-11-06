"""La medición de memoria disponible, que decide si cabe un modelo."""
import builtins

from backend import memoria


def test_devuelve_los_gib_disponibles_del_sistema():
    gb = memoria.disponible_gb()
    # No se fija un número —depende de la máquina— pero sí que sea una medida
    # creíble: nadie tiene 0 GiB disponibles ni 10 TiB.
    assert gb is not None and 0.1 < gb < 10240


def test_sin_psutil_devuelve_none_en_vez_de_reventar(monkeypatch):
    """Quien la llama está decidiendo si arrancar un modelo o esperar: quedarse
    sin medición no puede ser peor que no mirar, y nunca puede tumbar la etapa."""
    real = builtins.__import__

    def sin_psutil(nombre, *args, **kwargs):
        if nombre == "psutil":
            raise ImportError("no está")
        return real(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_psutil)
    assert memoria.disponible_gb() is None


def test_si_psutil_falla_por_dentro_tampoco_revienta(monkeypatch):
    import psutil

    def explota():
        raise OSError("vm_stat no responde")

    monkeypatch.setattr(psutil, "virtual_memory", explota)
    assert memoria.disponible_gb() is None


# --- el contador de swap ----------------------------------------------------
# La memoria disponible dice si algo cabe ahora; esto dice si lo que ya corrió
# cupo. Al terminar una etapa, la disponible vuelve a parecer sana y el único
# rastro de que el equipo ha estado paginando es este contador.

def test_los_swapouts_son_una_cifra_creible():
    gb = memoria.swapouts_gb()
    # Acumulado desde el arranque del equipo: puede ser 0 en uno recién
    # encendido, pero no negativo ni petabytes.
    assert gb is not None and 0 <= gb < 1_000_000


def test_mide_swapouts_y_no_pageouts(monkeypatch):
    """La trampa de este contador. `Pageouts` cuenta también las escrituras de
    archivos mapeados, que son normales: en este equipo daba 276 MiB frente a
    los 123 GiB de `Swapouts`. Y `psutil.swap_memory().sout`, que es lo que
    había a mano, devuelve en macOS justo el Pageouts."""
    import subprocess

    salida = (
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages free:                       1200346.\n"
        "Pageouts:                           16842.\n"
        "Swapouts:                         7517499.\n"
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, salida, "")
    )
    # 7517499 páginas de 16 KiB, no 16842.
    assert round(memoria.swapouts_gb(), 1) == 114.7


def test_sin_el_campo_devuelve_none(monkeypatch):
    """Un `vm_stat` de otro sistema operativo, o que cambie de formato: la cola
    lo llama con el job ya terminado y no puede estropearlo."""
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "nada que ver\n", ""),
    )
    assert memoria.swapouts_gb() is None


def test_si_vm_stat_no_esta_tampoco_revienta(monkeypatch):
    import subprocess

    def explota(*a, **k):
        raise FileNotFoundError("vm_stat")

    monkeypatch.setattr(subprocess, "run", explota)
    assert memoria.swapouts_gb() is None


# --- los topes del asignador de MPS -----------------------------------------
# Lo que mandaba la voz al swap: el asignador cachea lo que libera y en una
# generación autorregresiva cada paso pide una forma distinta, así que no
# reutiliza nada. Sin topes, narrar 200 palabras pedía un pico de 53,1 GiB en
# una máquina de 48 y mandaba 76 GiB al swap; con ellos, 15,6 y nada.

def test_importar_la_config_deja_los_topes_en_el_entorno():
    """Tienen que estar puestos *antes* de que torch inicialice el asignador, y
    lo único que garantiza eso es que los ponga `config`, porque en todo el
    backend `import torch` va dentro de las funciones."""
    import os

    from backend import config

    assert os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] == str(config.VOZ_MPS_TOPE)
    assert os.environ["PYTORCH_MPS_LOW_WATERMARK_RATIO"] == str(config.VOZ_MPS_TOPE_BAJO)


def test_si_los_exportas_tu_manda_lo_tuyo(monkeypatch):
    """`setdefault` y no `=`: el que sabe cuánta memoria tiene su Mac eres tú."""
    import importlib
    import os

    from backend import config

    monkeypatch.setitem(os.environ, "PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.9")
    importlib.reload(config)
    assert os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] == "0.9"
