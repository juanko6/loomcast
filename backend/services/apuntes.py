"""Apuntes del job en curso: lo que pasó por debajo del handler y el historial
tiene que conservar.

El log de un job es lo que devuelve su handler, y hay cosas que el handler no
sabe ni tiene por qué saber. La que motivó esto: cuánta memoria soltó ComfyUI
antes de cargar el LLM. Se mide dos capas más abajo, donde nadie escribe el log,
y es justo el dato que hace falta cuando el equipo se queda sin memoria — el
historial de la UI es lo que el usuario lee, así que ahí tiene que estar.

Mismo diseño que `progreso.py` y `parada.py`: un solo hueco en memoria, porque
la cola procesa de uno en uno, y un lock porque lo escribe el hilo del worker y
lo lee el que cierra el job.

Fuera de un job los apuntes se descartan en vez de acumularse. Quien anota está
dos capas por debajo y no sabe si hay un job abierto: el día que a alguien se le
llame desde un hilo HTTP (el semáforo del LLM, por ejemplo), esas líneas se
tirarían en vez de acabar pegadas al log del siguiente job que pasara por aquí.
"""
import threading

_lock = threading.Lock()
_abierto = False
_lineas: list[str] = []


def iniciar() -> None:
    """Abre el hueco para el job que empieza y tira lo que hubiera."""
    global _abierto, _lineas
    with _lock:
        _abierto, _lineas = True, []


def anotar(linea: str) -> None:
    with _lock:
        if _abierto:
            _lineas.append(linea)


def recoger() -> list[str]:
    with _lock:
        return list(_lineas)


def limpiar() -> None:
    global _abierto, _lineas
    with _lock:
        _abierto, _lineas = False, []
