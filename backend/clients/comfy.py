"""Adaptador de ComfyUI: encola workflows, espera el resultado y descarga
imágenes. Los workflows base viven en workflows/*.json."""
import json
import time
from pathlib import Path

import httpx

from ..config import (
    COMFY_TIMEOUT_S,
    COMFY_URL,
    I2V_FRAMES,
    I2V_WORKFLOW,
    IMAGEN_HEIGHT,
    IMAGEN_MOTOR_EDITAR,
    IMAGEN_MOTOR_GENERAR,
    IMAGEN_MOTORES,
    IMAGEN_WIDTH,
    MUSICA_WORKFLOW,
    ROOT,
)

WORKFLOW_ESRGAN = ROOT / "workflows" / "esrgan_api.json"
TIMEOUT_S = COMFY_TIMEOUT_S
EXT_VIDEO = (".mp4", ".webm", ".mkv", ".mov", ".gif")
EXT_AUDIO = (".flac", ".mp3", ".wav", ".opus", ".ogg", ".m4a")


class ComfyError(RuntimeError):
    pass


def _render(crudo: str, **valores) -> dict:
    """Sustituye los placeholders de un workflow y devuelve el JSON resultante.

    Los placeholders de texto ({PROMPT}, {IMAGE}, {TAGS}…) viven dentro de
    comillas y se escapan para no romper el JSON. Los numéricos ({SEED},
    {WIDTH}, {FRAMES}…) van **entrecomillados en el archivo** y se sustituyen
    incluyendo las comillas: así el workflow sigue siendo JSON válido y se puede
    abrir tal cual en ComfyUI, pero ComfyUI recibe el número.
    """
    for clave, valor in valores.items():
        marca = "{" + clave + "}"
        if isinstance(valor, str):
            crudo = crudo.replace(marca, json.dumps(valor)[1:-1])
        else:
            crudo = crudo.replace(f'"{marca}"', str(valor))
    faltan = [m for m in valores if "{" + m + "}" in crudo]
    if faltan:
        raise ComfyError(f"Placeholders sin sustituir en el workflow: {faltan}")
    return json.loads(crudo)


def _workflow_motor(motor_id: str | None, modo: str) -> Path:
    """Ruta del workflow que un motor usa para `modo` (generar | editar)."""
    motor_id = motor_id or (
        IMAGEN_MOTOR_GENERAR if modo == "generar" else IMAGEN_MOTOR_EDITAR
    )
    motor = IMAGEN_MOTORES.get(motor_id)
    if motor is None:
        raise ComfyError(
            f"Motor de imagen desconocido: '{motor_id}'. "
            f"Declarados en config.toml: {sorted(IMAGEN_MOTORES)}"
        )
    relativa = motor.workflow(modo)
    if relativa is None:
        raise ComfyError(f"El motor '{motor.nombre}' no sabe {modo} imágenes")
    ruta = ROOT / relativa
    if not ruta.exists():
        raise ComfyError(
            f"No existe el workflow de {modo} del motor '{motor.nombre}' en {ruta}. "
            "Expórtalo de ComfyUI en formato API con sus placeholders y un nodo "
            "SaveImage, o ajusta config.toml [imagen.motores]."
        )
    return ruta


def _encolar_y_esperar(c: httpx.Client, workflow: dict) -> dict:
    """Encola el workflow y espera a que termine; devuelve su entry del history."""
    r = c.post(f"{COMFY_URL}/prompt", json={"prompt": workflow})
    if r.status_code >= 400:
        raise ComfyError(f"ComfyUI rechazó el workflow: {r.text[:300]}")
    pid = r.json()["prompt_id"]

    inicio = time.time()
    while True:
        hist = c.get(f"{COMFY_URL}/history/{pid}").json()
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise ComfyError(json.dumps(entry.get("status"))[:500])
            if status.get("completed"):
                return entry
        if time.time() - inicio > TIMEOUT_S:
            raise ComfyError(f"Timeout esperando el workflow (prompt {pid})")
        time.sleep(2)


def _descargar_primera_imagen(c: httpx.Client, entry: dict, destino: Path) -> None:
    imagenes = [
        img
        for out in entry.get("outputs", {}).values()
        for img in out.get("images", [])
    ]
    if not imagenes:
        raise ComfyError("El workflow terminó sin imágenes")
    img = imagenes[0]
    r = c.get(
        f"{COMFY_URL}/view",
        params={
            "filename": img["filename"],
            "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output"),
        },
    )
    if r.status_code >= 400:
        raise ComfyError(f"No se pudo descargar {img['filename']}")
    destino.write_bytes(r.content)


def _descargar_primer_video(c: httpx.Client, entry: dict, destino: Path) -> None:
    """Descarga el primer archivo de video de la salida (VHS_VideoCombine,
    SaveVideo, etc.). ComfyUI lo expone bajo claves como 'gifs' o 'videos'."""
    archivos = [
        f
        for out in entry.get("outputs", {}).values()
        for clave, lista in out.items()
        if isinstance(lista, list)
        for f in lista
        if isinstance(f, dict) and "filename" in f
    ]
    videos = [f for f in archivos if f["filename"].lower().endswith(EXT_VIDEO)]
    elegido = (videos or archivos)
    if not elegido:
        raise ComfyError(
            "El workflow i2v terminó sin producir un archivo de video. "
            "Revisa que tenga un nodo de guardado (VHS_VideoCombine / SaveVideo)."
        )
    f = elegido[0]
    r = c.get(
        f"{COMFY_URL}/view",
        params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                "type": f.get("type", "output")},
    )
    if r.status_code >= 400:
        raise ComfyError(f"No se pudo descargar {f['filename']}")
    destino.write_bytes(r.content)


def _descargar_primer_audio(c: httpx.Client, entry: dict, destino: Path) -> Path:
    """Descarga el primer archivo de audio de la salida (SaveAudio, SaveAudioMP3,
    etc.). ComfyUI lo expone bajo la clave 'audio' del output. Conserva la
    extensión de origen (FLAC/MP3/WAV…) escribiendo en `destino` con ese sufijo;
    devuelve la ruta final escrita."""
    archivos = [
        f
        for out in entry.get("outputs", {}).values()
        for lista in out.values()
        if isinstance(lista, list)
        for f in lista
        if isinstance(f, dict) and "filename" in f
    ]
    audios = [f for f in archivos if f["filename"].lower().endswith(EXT_AUDIO)]
    elegido = audios or archivos
    if not elegido:
        raise ComfyError(
            "El workflow de música terminó sin producir un archivo de audio. "
            "Revisa que tenga un nodo de guardado (SaveAudio / SaveAudioMP3)."
        )
    f = elegido[0]
    r = c.get(
        f"{COMFY_URL}/view",
        params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                "type": f.get("type", "output")},
    )
    if r.status_code >= 400:
        raise ComfyError(f"No se pudo descargar {f['filename']}")
    ext = Path(f["filename"]).suffix.lower() or ".flac"
    final = destino.with_suffix(ext)
    final.write_bytes(r.content)
    return final


def _subir_imagen(c: httpx.Client, origen: Path) -> str:
    """Sube una imagen al input/ de ComfyUI; devuelve el nombre con el que quedó."""
    r = c.post(
        f"{COMFY_URL}/upload/image",
        files={"image": (origen.name, origen.read_bytes(), "image/png")},
        data={"overwrite": "true"},
    )
    if r.status_code >= 400:
        raise ComfyError(f"No se pudo subir {origen.name}: {r.text[:200]}")
    return r.json()["name"]


def generar_imagen(
    prompt: str,
    seed: int,
    destino: Path,
    width: int | None = None,
    height: int | None = None,
    motor: str | None = None,
) -> None:
    """Genera una imagen desde texto con el motor indicado y la guarda en
    `destino`.

    `motor` es un id de [imagen.motores] de config.toml; None usa el de
    [imagen].motor_generar. Con `width`/`height` a None se usa el tamaño por
    defecto de config (lo que hace el pipeline de vídeo)."""
    wf_path = _workflow_motor(motor, "generar")
    with httpx.Client(timeout=30) as c:
        wf = _render(
            wf_path.read_text(),
            PROMPT=prompt,
            SEED=seed,
            WIDTH=width if width is not None else IMAGEN_WIDTH,
            HEIGHT=height if height is not None else IMAGEN_HEIGHT,
        )
        entry = _encolar_y_esperar(c, wf)
        _descargar_primera_imagen(c, entry, destino)


def editar_imagen(
    imagen: Path,
    prompt: str,
    seed: int,
    destino: Path,
    motor: str | None = None,
) -> None:
    """Edita una imagen con el motor instruct-edit indicado y guarda el
    resultado en `destino`.

    `motor` es un id de [imagen.motores] de config.toml; None usa el de
    [imagen].motor_editar. El workflow debe traer los placeholders {IMAGE},
    {PROMPT} y {SEED}."""
    wf_path = _workflow_motor(motor, "editar")
    with httpx.Client(timeout=30) as c:
        nombre = _subir_imagen(c, imagen)
        wf = _render(wf_path.read_text(), IMAGE=nombre, PROMPT=prompt, SEED=seed)
        entry = _encolar_y_esperar(c, wf)
        _descargar_primera_imagen(c, entry, destino)


def upscale_imagen(origen: Path, destino: Path) -> None:
    """Reescala una imagen con Real-ESRGAN x4 y la guarda en `destino`."""
    with httpx.Client(timeout=30) as c:
        nombre = _subir_imagen(c, origen)
        wf = json.loads(WORKFLOW_ESRGAN.read_text())
        wf["load"]["inputs"]["image"] = nombre
        entry = _encolar_y_esperar(c, wf)
        _descargar_primera_imagen(c, entry, destino)


def generar_video_i2v(imagen: Path, prompt: str, seed: int, destino: Path) -> None:
    """Anima una imagen con el workflow i2v configurable (LTX, WAN, etc.).

    El workflow (config: [i2v].workflow) debe traer los placeholders {IMAGE},
    {PROMPT}, {SEED} y {FRAMES} en cualquier valor de sus nodos. Los numéricos
    ({SEED}, {FRAMES}) van entrecomillados en el JSON; ver `_render`.
    """
    wf_path = ROOT / I2V_WORKFLOW
    if not wf_path.exists():
        raise ComfyError(
            f"No existe el workflow i2v en {wf_path}. Exporta tu workflow de "
            "ComfyUI en formato API con los placeholders {IMAGE}, {PROMPT}, "
            "{SEED} y {FRAMES}, y ponlo en esa ruta (o ajusta config.toml "
            "[i2v].workflow)."
        )
    with httpx.Client(timeout=30) as c:
        nombre = _subir_imagen(c, imagen)
        wf = _render(
            wf_path.read_text(),
            IMAGE=nombre,
            PROMPT=prompt,
            SEED=seed,
            FRAMES=I2V_FRAMES,
        )
        entry = _encolar_y_esperar(c, wf)
        _descargar_primer_video(c, entry, destino)


def generar_musica(
    tags: str,
    lyrics: str,
    seed: int,
    duracion_s: int,
    destino: Path,
) -> Path:
    """Genera una pista de música con el workflow ACE-Step configurable y la
    guarda junto a `destino` conservando la extensión de origen (devuelve la
    ruta final).

    El workflow (config: [musica].workflow) debe traer los placeholders
    {TAGS}, {LYRICS}, {SEED} y {DURACION}, y terminar en un nodo de guardado de
    audio (SaveAudio / SaveAudioMP3). Los numéricos ({SEED}, {DURACION}) van
    entrecomillados en el JSON; ver `_render`.
    """
    wf_path = ROOT / MUSICA_WORKFLOW
    if not wf_path.exists():
        raise ComfyError(
            f"No existe el workflow de música en {wf_path}. Exporta la plantilla "
            "ACE-Step de ComfyUI en formato API con los placeholders {TAGS}, "
            "{LYRICS}, {SEED} y {DURACION} (y un nodo SaveAudio), y ponlo en esa "
            "ruta (o ajusta config.toml [musica].workflow)."
        )
    with httpx.Client(timeout=30) as c:
        wf = _render(
            wf_path.read_text(),
            TAGS=tags,
            LYRICS=lyrics,
            SEED=seed,
            DURACION=duracion_s,
        )
        entry = _encolar_y_esperar(c, wf)
        return _descargar_primer_audio(c, entry, destino)


def liberar_memoria() -> None:
    """Descarga los modelos de ComfyUI de la memoria unificada."""
    try:
        with httpx.Client(timeout=15) as c:
            c.post(
                f"{COMFY_URL}/free",
                json={"unload_models": True, "free_memory": True},
            )
    except httpx.HTTPError:
        pass
