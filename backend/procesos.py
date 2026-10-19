"""Ejecución de procesos externos (ffmpeg, ffprobe, RIFE) siempre con tope de tiempo.

Un `subprocess.run` sin `timeout` puede dejar un job corriendo para siempre —y
con él a toda la cola, que procesa de uno en uno— si el proceso se queda
esperando (ffmpeg con `-loop 1` y una imagen que no decodifica, un RIFE que
cuelga la GPU…). Aquí cada llamada declara cuánto puede tardar y, si se pasa, el
proceso se mata y sube un error legible en vez de un cuelgue.
"""
import subprocess
import threading
import time

# Topes por tipo de trabajo, en segundos. Generosos a propósito: el objetivo es
# cortar lo que no va a terminar nunca, no apurar lo lento (un montaje con 100
# subtítulos superpuestos tarda minutos en el M3 Max).
SONDEO_S = 30            # ffprobe
CORTO_S = 120            # conversiones de audio, recortes
MASTERIZADO_S = 600      # loudnorm, dos pasadas
CLIP_S = 900             # un clip de una escena
RIFE_S = 1800            # interpolar un clip
MONTAJE_S = 3600         # armado final del video


# Lo que se le da a un proceso para morir por las buenas antes de matarlo. Se
# le manda SIGTERM primero porque ffmpeg cierra el archivo que estaba
# escribiendo en vez de dejar el descriptor a medias; al que lo ignore se le
# manda SIGKILL, porque parar no puede quedarse esperando a un proceso sordo.
PARADA_S = 5


class ProcesoTimeout(RuntimeError):
    """El proceso superó su tope y se canceló."""


class ProcesoParado(RuntimeError):
    """El proceso se cortó porque se pidió parar el job (no es un fallo suyo)."""


# Procesos externos vivos ahora mismo, para poder pararlos desde el hilo HTTP
# cuando el usuario pide detener la generación. La cola es de un solo hilo, así
# que lo normal es que haya uno; se guarda un conjunto porque una etapa puede
# arrancar varios seguidos y el registro no debe depender de ese detalle.
_lock = threading.Lock()
_vivos: set[subprocess.Popen] = set()
# Los que matamos nosotros: su código de salida no es un fallo del proceso, es la
# parada, y quien llamó tiene que poder distinguirlo. Se guardan los objetos y no
# sus pids porque el sistema reutiliza los pids: un número que se quedara aquí
# por una carrera acabaría marcando como "parado" a un proceso inocente.
_parados: set[subprocess.Popen] = set()


def terminar_actual() -> int:
    """Corta los procesos externos en marcha. Devuelve cuántos había.

    La llama el hilo HTTP, no el worker: parar es una petición de fuera y el
    hilo de la cola está bloqueado esperando a que el proceso termine.
    """
    with _lock:
        procesos = list(_vivos)
        _parados.update(procesos)
    for p in procesos:
        p.terminate()
    plazo = time.monotonic() + PARADA_S
    for p in procesos:
        while p.poll() is None and time.monotonic() < plazo:
            time.sleep(0.05)
        if p.poll() is None:
            p.kill()
    with _lock:
        # El que ya no esté vivo es que terminó por su cuenta justo antes de la
        # señal, y `ejecutar` ya leyó su marca: dejarla aquí sería basura.
        _parados.intersection_update(_vivos)
    return len(procesos)


def ejecutar(cmd: list[str], *, timeout: float, que: str = "", **kw) -> subprocess.CompletedProcess:
    """Lanza el proceso con tope obligatorio y sin terminal, y espera a que
    termine. Devuelve lo mismo que `subprocess.run` (admite sus `capture_output`,
    `text`, `check`, `cwd`…). `que` nombra la tarea en el error.

    **stdin va a /dev/null a propósito.** ffmpeg lee stdin para sus teclas
    interactivas (`q` para parar), y si hereda la terminal estando en un grupo
    de procesos en segundo plano —que es lo que pasa al arrancar con
    `scripts/run-loomcast.sh`, porque su `set -m` da un grupo propio a cada
    servicio— el kernel le manda SIGTTIN y **suspende el grupo entero**: el
    backend se queda congelado, sin consumir CPU, hasta que algo le mande
    SIGCONT. Visto el 2026-10-12 generando la voz: el ffmpeg del atempo se
    suspendió, agotó sus 120 s y el job murió por timeout sin motivo aparente.
    """
    if kw.pop("capture_output", False):
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
    check = kw.pop("check", False)
    tarea = que or cmd[0]
    # Popen y no `subprocess.run`: run no deja ver el proceso mientras corre, y
    # sin esa referencia no hay forma de pedirle que termine cuando el usuario
    # para la generación.
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, **kw)
    with _lock:
        _vivos.add(proc)
    try:
        salida, error = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise ProcesoTimeout(
            f"{tarea} no terminó en {timeout:.0f} s; se cancela para no dejar "
            "el job colgado"
        ) from None
    finally:
        with _lock:
            _vivos.discard(proc)
            parado = proc in _parados
            _parados.discard(proc)
    if parado:
        raise ProcesoParado(f"{tarea} se paró a petición del usuario")
    r = subprocess.CompletedProcess(proc.args, proc.returncode, salida, error)
    if check:
        r.check_returncode()
    return r
