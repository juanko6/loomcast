"""Ciclo de vida del llama-server: se carga cuando una etapa de texto lo
necesita y se descarga cuando hay que dejarle la memoria unificada a otro modelo.

El LLM es el residente más caro del equipo (decenas de GB) y el que menos
trabaja: solo cuatro etapas del pipeline lo usan (ideas, guion, metadatos y
prompts de escena). ComfyUI y Qwen3-TTS ya sueltan sus pesos al terminar; esto
hace lo propio con llama-server, que hasta ahora se quedaba residente.

Reglas:
  - Solo se para lo que Loomcast arrancó. Si encuentra un llama-server ya
    escuchando en la url del modelo, lo adopta y no lo toca: puede ser tuyo.
  - Un modelo sin `comando` en config.toml es externo y nunca se gestiona.
  - El modelo activo se elige desde la UI y se guarda en la BD.
"""
import contextlib
import json
import os
import signal
import subprocess
import threading
import time

from .. import memoria
from ..clients import comfy, llm
from ..config import (
    LLM_AUTOSTART,
    LLM_ESPERA_ARRANQUE_S,
    LLM_ESPERA_DEVOLUCION_S,
    LLM_INACTIVIDAD_S,
    LLM_LOGS_DIR,
    LLM_MODELOS,
    ROOT,
    ModeloLLM,
)
from ..db import get_session
from ..repositories import ajustes as ajustes_repo
from . import apuntes

CLAVE_AJUSTE = "llm_modelo"
# Cada cuánto comprueba el vigilante si el modelo lleva demasiado ocioso.
LATIDO_S = 10
# Margen para que el proceso muera por las buenas antes del SIGKILL.
GRACIA_S = 20
# Rastro del proceso en marcha, para recuperarlo si Loomcast muere de golpe.
ARCHIVO_PID = LLM_LOGS_DIR / "llm.pid"


class LLMProcesoError(RuntimeError):
    pass


_lock = threading.RLock()
_proc: subprocess.Popen | None = None  # solo si lo arrancamos nosotros
_proc_modelo: str = ""  # id del modelo que corre en _proc
_ultimo_uso: float = 0.0
_en_curso: int = 0  # etapas de texto en vuelo


# ---------- modelos declarados ----------

def modelos() -> list[ModeloLLM]:
    return LLM_MODELOS


def por_id(modelo_id: str) -> ModeloLLM | None:
    return next((m for m in LLM_MODELOS if m.id == modelo_id), None)


def activo() -> ModeloLLM:
    """El modelo elegido en la UI; el primero de config.toml si no hay ninguno."""
    with get_session() as s:
        guardado = ajustes_repo.leer(s, CLAVE_AJUSTE)
    return (por_id(guardado) if guardado else None) or LLM_MODELOS[0]


def seleccionar(modelo_id: str) -> ModeloLLM:
    """Cambia el modelo activo. Si hay otro cargado y la cola está libre, lo
    descarga ya; si está trabajando, el relevo ocurre en el siguiente job."""
    modelo = por_id(modelo_id)
    if modelo is None:
        raise ValueError(f"No hay ningún modelo con id «{modelo_id}» en config.toml")
    with get_session() as s:
        ajustes_repo.escribir(s, CLAVE_AJUSTE, modelo.id)
        s.commit()
    with _lock:
        llm.configurar(modelo)
        if _proc_modelo and _proc_modelo != modelo.id and not _en_curso:
            _detener(f"cambio a «{modelo.nombre}»")
    return modelo


# ---------- proceso ----------

def _ultimas_lineas(ruta, n: int = 15) -> str:
    try:
        return "\n".join(ruta.read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return "(sin log)"


def _matar(proc: subprocess.Popen) -> None:
    """SIGTERM al grupo entero: el comando es un script de shell y el
    llama-server real es su hijo, así que matar solo al shell lo dejaría vivo."""
    try:
        grupo = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(grupo, signal.SIGTERM)
    try:
        proc.wait(timeout=GRACIA_S)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(grupo, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)


def _vive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _matar_pgid(pgid: int) -> None:
    """Mata un grupo que no es hijo nuestro (un huérfano de otra ejecución)."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signal.SIGTERM)
    fin = time.monotonic() + GRACIA_S
    while time.monotonic() < fin and _vive(pgid):
        time.sleep(0.5)
    if _vive(pgid):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def _inicio_proceso(pgid: int) -> str:
    """Instante de arranque del proceso. Es lo que permite distinguirlo de un
    pid reciclado: la línea de comandos no vale, porque el `sh -c` hace exec
    sobre el binario y deja de parecerse al comando que escribiste."""
    try:
        return subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pgid)],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _anotar_pid(modelo: ModeloLLM, proc: subprocess.Popen) -> None:
    with contextlib.suppress(OSError):
        pgid = os.getpgid(proc.pid)
        ARCHIVO_PID.write_text(json.dumps({
            "modelo": modelo.id,
            "pgid": pgid,
            "inicio": _inicio_proceso(pgid),
        }))


def _olvidar_pid() -> None:
    with contextlib.suppress(OSError):
        ARCHIVO_PID.unlink(missing_ok=True)


def _reclamar_huerfano() -> None:
    """Si Loomcast murió a lo bruto (SIGKILL, cuelgue, reinicio), el
    llama-server que había arrancado sigue vivo ocupando la RAM: nadie quedó
    para pararlo. Al volver a arrancar se recupera esa memoria."""
    try:
        datos = json.loads(ARCHIVO_PID.read_text())
    except (OSError, ValueError):
        return
    _olvidar_pid()
    pgid, inicio = datos.get("pgid"), datos.get("inicio")
    if not pgid or not _vive(pgid):
        return
    # El pid pudo reciclarse mientras Loomcast estaba caído: si lo que corre
    # ahora con ese pid no arrancó en el mismo instante, no es nuestro modelo
    # y no se toca.
    if not inicio or _inicio_proceso(pgid) != inicio:
        return
    print(
        f"[llm] descargando «{datos.get('modelo')}», huérfano de una ejecución "
        "anterior de Loomcast",
        flush=True,
    )
    _matar_pgid(pgid)


def _esperar_puerto_libre(url: str, limite_s: float = 15) -> None:
    """Tus modelos suelen compartir puerto: hasta que el que muere no lo suelta,
    el siguiente no puede escuchar."""
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin and llm.ping(url):
        time.sleep(0.5)


def _lanzar(modelo: ModeloLLM) -> subprocess.Popen:
    LLM_LOGS_DIR.mkdir(exist_ok=True)
    log = LLM_LOGS_DIR / f"llm-{modelo.id}.log"
    print(f"[llm] arrancando «{modelo.nombre}» → {log}", flush=True)
    with open(log, "wb") as f:
        proc = subprocess.Popen(
            modelo.comando,
            shell=True,  # es tu script tal cual: admite ~, variables y argumentos
            cwd=ROOT,
            stdin=subprocess.DEVNULL,  # ver el porqué en backend/procesos.py
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # grupo propio, para poder matar también a sus hijos
        )
    fin = time.monotonic() + LLM_ESPERA_ARRANQUE_S
    while time.monotonic() < fin:
        if proc.poll() is not None:
            raise LLMProcesoError(
                f"El comando de «{modelo.nombre}» terminó solo (código "
                f"{proc.returncode}) sin dejar el servidor escuchando en "
                f"{modelo.url}. Últimas líneas de {log}:\n{_ultimas_lineas(log)}"
            )
        if llm.ping(modelo.url):
            print(f"[llm] «{modelo.nombre}» listo", flush=True)
            _anotar_pid(modelo, proc)
            return proc
        time.sleep(0.5)
    _matar(proc)
    raise LLMProcesoError(
        f"«{modelo.nombre}» no respondió en {modelo.url} tras "
        f"{LLM_ESPERA_ARRANQUE_S:.0f}s. Sube [llm].espera_arranque_s si el "
        f"modelo tarda más en cargar. Últimas líneas de {log}:\n"
        f"{_ultimas_lineas(log)}"
    )


def _detener(motivo: str) -> None:
    """Para el llama-server gestionado. Asume el lock tomado."""
    global _proc, _proc_modelo
    if _proc is None:
        return
    modelo = por_id(_proc_modelo)
    if _proc.poll() is None:
        print(f"[llm] parando «{_proc_modelo}»: {motivo}", flush=True)
        _matar(_proc)
        if modelo:
            _esperar_puerto_libre(modelo.url)
    _olvidar_pid()
    _proc, _proc_modelo = None, ""


# ---------- API para el worker ----------

def _hacer_sitio(modelo: ModeloLLM) -> None:
    """Pide a ComfyUI que suelte la memoria y no vuelve hasta comprobarlo.

    Lo que hacía antes era mandar el `POST /free` y lanzar el modelo acto
    seguido, y eso es lo que mató al backend con `Killed: 9` el 2026-10-19:
    `/free` solo enciende una bandera en la cola de ComfyUI y devuelve 200 en
    1 ms con los 11,7 GiB de Z-Image todavía dentro, así que el MLX de ~20 GiB
    arrancó sobre una memoria que nadie había liberado. El kernel eligió a quién
    matar y eligió al backend: SIGKILL, sin excepción ni traza.

    Peor aún, medido: durante la descarga la memoria libre **baja** antes de
    subir (16,4 → 10,0 → 27,0 GiB), porque mover los pesos al dispositivo de
    offload duplica un instante las copias en la misma memoria unificada. El
    momento justo después del POST es el peor de todos.

    Si la memoria no llega, se lanza en vez de arrancar el modelo: el job sale
    como error con el antes/después medido, que es información, y no como un
    backend muerto, que no es ninguna.
    """
    lib = comfy.liberar_memoria(hasta_gb=modelo.memoria_gb)
    linea = f"Memoria para «{modelo.nombre}» ({modelo.memoria_gb:.0f} GiB): {lib}"
    print(f"[llm] {linea}", flush=True)
    apuntes.anotar(linea)
    if lib.logrado:
        return
    # A quién mirar depende de si ComfyUI recogió la petición: si no respondió,
    # no tiene nada cargado que soltar y señalarlo manda a buscar donde no es.
    culpable = (
        "ComfyUI no está escuchando, así que la memoria la tiene otra cosa: "
        "mira si quedó algún llama-server o mlx_lm suelto, y cuánta memoria "
        "está comprimida (`vm_stat`: el compresor puede quedarse con decenas de "
        "GiB tras un pico de swap, y esa no vuelve sola)"
        if lib.peticiones == 0
        else "mira si ComfyUI tiene un workflow en marcha —solo atiende el "
        "/free entre prompts—, si quedó algún llama-server suelto, o si hay "
        "otra cosa ocupándola"
    )
    raise LLMProcesoError(
        f"No se lanza «{modelo.nombre}»: no hay memoria. Necesita "
        f"{modelo.memoria_gb:.0f} GiB libres y quedan {lib.despues_gb:.1f} "
        f"({lib.antes_gb:.1f} al empezar), tras {lib.espera_s:.0f} s de espera. "
        "Lanzarlo igualmente es lo que hace que el kernel mate al backend con "
        f"Killed: 9. {culpable}. Si tu equipo es más pequeño, baja "
        "[llm].memoria_gb (o el del modelo) a lo que de verdad necesite."
    )


def asegurar() -> ModeloLLM:
    """Deja al modelo activo listo para responder. Devuelve cuál es."""
    global _proc, _proc_modelo, _ultimo_uso
    with _lock:
        modelo = activo()
        llm.configurar(modelo)
        _ultimo_uso = time.monotonic()

        if not modelo.gestionado:
            return modelo  # externo: lo levantas tú
        if _proc is not None and _proc.poll() is None:
            if _proc_modelo == modelo.id:
                return modelo  # ya cargado
            _detener(f"cambio a «{modelo.nombre}»")
        if llm.ping(modelo.url):
            return modelo  # ya había uno escuchando; se adopta y no se toca
        _hacer_sitio(modelo)
        _proc = _lanzar(modelo)
        _proc_modelo = modelo.id
        return modelo


# Qué parte de lo que ocupaba el modelo hay que ver volver para dar la memoria
# por devuelta. No el 100 %: entre el compresor, la fragmentación y lo que el
# propio backend tenga dentro, esperar a recuperarlo todo sería agotar el tope
# siempre. Con tres cuartos, lo que falta ya no es un modelo entero.
DEVUELTA = 0.75


def _esperar_devolucion(memoria_gb: float, antes: float | None) -> None:
    """Espera a que el sistema reclame la memoria del modelo que acabamos de
    matar, antes de dejar que la etapa siguiente cargue la suya.

    `_matar` espera a que el proceso muera y a que su puerto quede libre, pero
    eso no es lo mismo que tener la memoria de vuelta: el kernel tarda en
    reclamar 22 GiB, y el 2026-10-20, generando la voz de un episodio de serie,
    el TTS empezó a cargar justo detrás y el pico se fue casi 20 GiB al swap.

    Es el mismo error que ya nos costó un `Killed: 9` con el `/free` de ComfyUI,
    en el otro sentido: allí no esperábamos a que soltara, aquí no esperábamos a
    que el sistema recogiera. Nunca falla: la etapa siguiente tiene que correr
    igual, así que si la memoria no vuelve se anota y se sigue.
    """
    if memoria_gb <= 0 or antes is None or LLM_ESPERA_DEVOLUCION_S <= 0:
        return
    objetivo = antes + memoria_gb * DEVUELTA
    inicio = time.monotonic()
    fin = inicio + LLM_ESPERA_DEVOLUCION_S
    libre = antes
    while True:
        libre = memoria.disponible_gb()
        if libre is None or libre >= objetivo or time.monotonic() >= fin:
            break
        time.sleep(0.25)
    espera = time.monotonic() - inicio
    if libre is None:
        return
    linea = (
        f"Memoria devuelta: {antes:.1f} → {libre:.1f} GiB "
        f"({libre - antes:+.1f} de los {memoria_gb:.0f} que ocupaba, "
        f"en {espera:.1f} s)"
    )
    print(f"[llm] {linea}", flush=True)
    apuntes.anotar(linea)


def liberar(motivo: str) -> None:
    """Descarga el LLM antes de una etapa de voz/GPU que necesita la memoria.

    No vuelve hasta ver la memoria de vuelta (ver `_esperar_devolucion`): quien
    llama lo hace para que quepa lo suyo, y devolverle el control antes de que
    el kernel haya reclamado el modelo es mandarlo al swap.
    """
    with _lock:
        modelo = por_id(_proc_modelo)
        habia = _proc is not None and _proc.poll() is None
        antes = memoria.disponible_gb() if habia else None
        _detener(motivo)
        if habia and modelo:
            _esperar_devolucion(modelo.memoria_gb, antes)


@contextlib.contextmanager
def en_uso():
    """Envuelve una etapa de texto: carga el modelo y lo protege del vigilante
    de inactividad mientras dura (una etapa larga no debe descargarse a medias)."""
    global _en_curso, _ultimo_uso
    asegurar()
    with _lock:
        _en_curso += 1
    try:
        yield
    finally:
        with _lock:
            _en_curso -= 1
            _ultimo_uso = time.monotonic()


# ---------- estado y arranque ----------

def estado() -> dict:
    """Para el semáforo de la UI. No toma el lock: debe responder al instante
    aunque haya una carga de modelo en curso."""
    modelo = activo()
    if not modelo.gestionado:
        return {
            "id": modelo.id,
            "nombre": modelo.nombre,
            "gestionado": False,
            "estado": "activo" if llm.ping(modelo.url) else "caido",
        }
    proc = _proc
    cargado = proc is not None and proc.poll() is None and _proc_modelo == modelo.id
    return {
        "id": modelo.id,
        "nombre": modelo.nombre,
        "gestionado": True,
        # en_espera no es un error: se cargará solo en la siguiente etapa de texto
        "estado": "cargado" if cargado else "en_espera",
    }


def _vigilar() -> None:
    while True:
        time.sleep(LATIDO_S)
        with _lock:
            if _proc is None or _en_curso or LLM_INACTIVIDAD_S <= 0:
                continue
            if time.monotonic() - _ultimo_uso >= LLM_INACTIVIDAD_S:
                _detener(f"{LLM_INACTIVIDAD_S:.0f}s sin usarse")


def arrancar() -> None:
    """Fija el modelo activo al iniciar el backend y lanza el vigilante."""
    _reclamar_huerfano()
    llm.configurar(activo())
    if LLM_AUTOSTART:
        threading.Thread(target=_vigilar, daemon=True, name="loomcast-llm").start()


def apagar() -> None:
    liberar("se apaga Loomcast")
