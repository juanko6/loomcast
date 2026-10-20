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
