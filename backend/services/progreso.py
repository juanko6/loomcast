"""Progreso del job en curso, para que la cola no sea una caja negra.

Las etapas que trabajan por lotes (una imagen por escena, un clip por escena)
tardan minutos y hasta ahora solo se veía "corriendo": ni por dónde iban ni si
seguían vivas. Aquí se anota por dónde va el lote y se estima lo que queda.

Vive en memoria y no en la BD a propósito: se escribe una vez por elemento, no
tiene ningún valor histórico y la BD es la misma SQLite que usa el worker. Como
la cola procesa de uno en uno (ver workers/queue.py), un único hueco basta.

El estado lo escribe el hilo del worker y lo leen los hilos que atienden las
peticiones HTTP, así que todo pasa por un lock.
"""
import threading
import time

_lock = threading.Lock()
_actual: dict | None = None


def iniciar(job_id: int, tipo: str) -> None:
    """Marca que empieza un job. Sin lote todavía: las etapas que no van por
    lotes (voz, guion, armado) se quedan solo con el tiempo transcurrido."""
    global _actual
    with _lock:
        _actual = {
            "job_id": job_id,
            "tipo": tipo,
            "t_job": time.time(),
            "hecho": 0,
            "total": 0,
            "unidad": "",
            # Instante y posición en que arrancó el lote, para estimar el resto
            # sobre lo que tarda de verdad en esta máquina.
            "t_lote": None,
            "base": 0,
        }


def lote(hecho: int, total: int, unidad: str = "elemento") -> None:
    """Anota que van `hecho` de `total` elementos completados.

    Se llama al principio de cada vuelta del bucle: al empezar el tercero hay
    dos hechos. `total` es lo que este job va a hacer de verdad, no el total del
    proyecto — los bucles reanudables saltan lo que ya estaba, y contar sobre el
    total dejaría la barra empezando por la mitad.
    """
    with _lock:
        if _actual is None:
            return
        _actual["hecho"], _actual["total"], _actual["unidad"] = hecho, total, unidad
        if _actual["t_lote"] is None:
            _actual["t_lote"], _actual["base"] = time.time(), hecho


def limpiar() -> None:
    global _actual
    with _lock:
        _actual = None


def snapshot() -> dict | None:
    """Lo que la API expone. None si no hay ningún job corriendo."""
    with _lock:
        if _actual is None:
            return None
        a = dict(_actual)

    ahora = time.time()
    total, hecho = a["total"], a["hecho"]
    datos = {
        "job_id": a["job_id"],
        "transcurrido_s": round(ahora - a["t_job"]),
        "fase": "",
        "hecho": hecho,
        "total": total,
        "pct": None,
        "eta_s": None,
    }
    if total <= 0:
        return datos

    datos["fase"] = f"{a['unidad']} {min(hecho + 1, total)} de {total}"
    datos["pct"] = round(100 * hecho / total)
    # El primer elemento del lote no da estimación: aún no hay nada medido y
    # inventar un número sería peor que no dar ninguno.
    completados = hecho - a["base"]
    if completados > 0 and a["t_lote"]:
        por_elemento = (ahora - a["t_lote"]) / completados
        datos["eta_s"] = round(por_elemento * (total - hecho))
    return datos
