"""Bandera de parada del job en curso, en el nivel más bajo del backend.

La enciende `services/cancelacion.py`, que además es quien corta ComfyUI y el
proceso externo. La bandera vive aquí abajo, al lado de `procesos.py`, porque la
miran también los `clients/*` —el LLM entre trozos de la respuesta, Whisper entre
segmentos— y un client no puede depender de la capa de servicios.

Quién la mira, y por tanto por dónde se puede cortar una etapa:

  - `clients/llm.py`: entre trozos de la respuesta en streaming. Cerrar la
    conexión hace que el servidor abandone la generación.
  - `clients/stt.py`: entre segmentos de Whisper, que se van decodificando.
  - `procesos.py`: no la mira, la usa al revés (lo matan desde fuera), pero su
    `ProcesoParado` es un `Parado` para que todo salga por el mismo sitio.
  - Los bucles por lotes del pipeline (una imagen o un clip por escena): entre
    elemento y elemento.

El estado es de memoria y de un solo hueco, como el de `services/progreso.py`: la
cola procesa de uno en uno. Lo escribe el hilo HTTP y lo lee el del worker, de
ahí el lock.
"""
import threading


class Parado(RuntimeError):
    """El trabajo se abandonó porque se pidió pararlo. No es un fallo."""


_lock = threading.Lock()
_job_id: int | None = None
_pedida = False


def iniciar(job_id: int) -> None:
    """Marca qué job empieza. Limpia cualquier petición anterior: una parada vale
    para el job al que se le pidió, no para el siguiente de la cola."""
    global _job_id, _pedida
    with _lock:
        _job_id, _pedida = job_id, False


def limpiar() -> None:
    global _job_id, _pedida
    with _lock:
        _job_id, _pedida = None, False


def marcar(job_id: int) -> bool:
    """Enciende la bandera si ese es el job en curso; devuelve si lo era."""
    global _pedida
    with _lock:
        if _job_id != job_id:
            return False
        _pedida = True
        return True


def pedida() -> bool:
    with _lock:
        return _pedida


def comprobar(que: str = "") -> None:
    """Sale por `Parado` si se pidió parar. La llaman los bucles por lotes entre
    elemento y elemento, que es donde cortar no deja nada a medias."""
    if pedida():
        raise Parado(f"Parado a petición del usuario{f' ({que})' if que else ''}")
