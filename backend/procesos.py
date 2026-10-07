"""Ejecución de procesos externos (ffmpeg, ffprobe, RIFE) siempre con tope de tiempo.

Un `subprocess.run` sin `timeout` puede dejar un job corriendo para siempre —y
con él a toda la cola, que procesa de uno en uno— si el proceso se queda
esperando (ffmpeg con `-loop 1` y una imagen que no decodifica, un RIFE que
cuelga la GPU…). Aquí cada llamada declara cuánto puede tardar y, si se pasa, el
proceso se mata y sube un error legible en vez de un cuelgue.
"""
import subprocess

# Topes por tipo de trabajo, en segundos. Generosos a propósito: el objetivo es
# cortar lo que no va a terminar nunca, no apurar lo lento (un montaje con 100
# subtítulos superpuestos tarda minutos en el M3 Max).
SONDEO_S = 30            # ffprobe
CORTO_S = 120            # conversiones de audio, recortes
MASTERIZADO_S = 600      # loudnorm, dos pasadas
CLIP_S = 900             # un clip de una escena
RIFE_S = 1800            # interpolar un clip
MONTAJE_S = 3600         # armado final del video


class ProcesoTimeout(RuntimeError):
    """El proceso superó su tope y se canceló."""


def ejecutar(cmd: list[str], *, timeout: float, que: str = "", **kw) -> subprocess.CompletedProcess:
    """`subprocess.run` con tope obligatorio. `que` nombra la tarea en el error."""
    try:
        return subprocess.run(cmd, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        tarea = que or cmd[0]
        raise ProcesoTimeout(
            f"{tarea} no terminó en {timeout:.0f} s; se cancela para no dejar "
            "el job colgado"
        ) from None
