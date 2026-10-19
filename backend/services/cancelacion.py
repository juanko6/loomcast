"""Parada en caliente del job que está corriendo.

Un job pendiente se cancela en la BD y el worker lo salta cuando le llega el
turno; eso no necesita nada de aquí. El que ya está corriendo es el difícil: el
hilo de la cola está bloqueado dentro del handler y hay que alcanzarlo desde el
hilo HTTP. Se corta por las tres vías por las que una etapa puede estar
esperando, porque cerrar solo una dejaría el job vivo:

  1. **ComfyUI** (imágenes, clips i2v, upscale, música): el trabajo corre dentro
     de ComfyUI y aquí solo se sondea su `/history`. Se le pide `/interrupt`, con
     lo que el prompt sube como fallido y la etapa sale.
  2. **Procesos externos** (ffmpeg, ESRGAN, RIFE): todos pasan por
     `backend/procesos.py`, que guarda el que está en marcha; se le manda
     SIGTERM y, si no muere, SIGKILL.
  3. **Los bucles por lotes** (una imagen por escena, un clip por escena): entre
     elemento y elemento miran esta bandera con `comprobar()` y salen por
     `Cancelado`, dejando hecho lo que ya estaba hecho. Sin esto, cortar el
     elemento en curso solo haría que la etapa empezara el siguiente.

El estado vive en memoria, como el de `progreso.py`: solo vale para el job en
curso y la cola procesa de uno en uno, así que un único hueco basta. Lo escribe
el hilo HTTP y lo lee el del worker, de ahí el lock.
"""
import threading

from .. import procesos
from ..clients import comfy


class Cancelado(RuntimeError):
    """El job se paró porque el usuario lo pidió (no es un fallo)."""


_lock = threading.Lock()
_job_id: int | None = None
_pedida = False


def iniciar(job_id: int) -> None:
    """Marca qué job empieza. Limpia cualquier petición anterior: una parada
    vale para el job al que se le pidió, no para el siguiente de la cola."""
    global _job_id, _pedida
    with _lock:
        _job_id, _pedida = job_id, False


def limpiar() -> None:
    global _job_id, _pedida
    with _lock:
        _job_id, _pedida = None, False


def pedir(job_id: int) -> bool:
    """Pide parar ese job. Devuelve si era el que estaba corriendo.

    Si no lo era, no hay nada que cortar: o ya terminó, o está esperando turno y
    basta con su estado en la BD.
    """
    global _pedida
    with _lock:
        if _job_id != job_id:
            return False
        _pedida = True
    # Fuera del lock: las dos llamadas hablan por red o esperan a un proceso, y
    # el worker tiene que poder leer la bandera mientras tanto.
    comfy.interrumpir()
    procesos.terminar_actual()
    return True


def pedida() -> bool:
    with _lock:
        return _pedida


def comprobar(que: str = "") -> None:
    """Sale por `Cancelado` si se pidió parar. La llaman los bucles por lotes
    entre elemento y elemento, que es donde cortar no deja nada a medias."""
    if pedida():
        raise Cancelado(f"Parado a petición del usuario{f' ({que})' if que else ''}")
