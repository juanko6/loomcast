"""Adaptador de ComfyUI: encola workflows, espera el resultado y descarga
imágenes. Los workflows base viven en workflows/*.json."""
import json
import time
from pathlib import Path

import httpx

from ..config import (
    COMFY_TIMEOUT_S,
    COMFY_URL,
    EDIT_WORKFLOW,
    I2V_FRAMES,
    I2V_WORKFLOW,
    MUSICA_WORKFLOW,
    ROOT,
)

WORKFLOW_ZIMAGE = ROOT / "workflows" / "z_image_turbo_api.json"
WORKFLOW_ESRGAN = ROOT / "workflows" / "esrgan_api.json"
TIMEOUT_S = COMFY_TIMEOUT_S
EXT_VIDEO = (".mp4", ".webm", ".mkv", ".mov", ".gif")
EXT_AUDIO = (".flac", ".mp3", ".wav", ".opus", ".ogg", ".m4a")


class ComfyError(RuntimeError):
    pass


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
) -> None:
    """Genera una imagen con Z-Image-Turbo y la guarda en `destino`.

    Con `width`/`height` se sobreescribe el tamaño del latente del workflow; si
    son None se respetan los valores del JSON (así la etapa de escenas del
    pipeline sigue funcionando sin cambios)."""
    wf = json.loads(WORKFLOW_ZIMAGE.read_text())
    wf["positive"]["inputs"]["text"] = prompt
    wf["sampler"]["inputs"]["seed"] = seed
    if width is not None:
        wf["latent"]["inputs"]["width"] = width
    if height is not None:
        wf["latent"]["inputs"]["height"] = height
    with httpx.Client(timeout=30) as c:
        entry = _encolar_y_esperar(c, wf)
        _descargar_primera_imagen(c, entry, destino)


def editar_imagen(imagen: Path, prompt: str, seed: int, destino: Path) -> None:
    """Edita una imagen con el workflow instruct-edit configurable y guarda el
    resultado en `destino`.

    El workflow (config: [edicion].workflow) debe traer los placeholders
    {IMAGE}, {PROMPT} y {SEED}, igual que el de i2v. {SEED} se sustituye sin
    comillas (valor numérico) y {PROMPT} escapado para vivir dentro del JSON."""
    wf_path = ROOT / EDIT_WORKFLOW
    if not wf_path.exists():
        raise ComfyError(
            f"No existe el workflow de edición en {wf_path}. Exporta tu workflow "
            "instruct-edit de ComfyUI en formato API con los placeholders "
            "{IMAGE}, {PROMPT} y {SEED} (y un nodo SaveImage), y ponlo en esa "
            "ruta (o ajusta config.toml [edicion].workflow)."
        )
    with httpx.Client(timeout=30) as c:
        nombre = _subir_imagen(c, imagen)
        crudo = wf_path.read_text()
        wf = json.loads(
            crudo.replace("{IMAGE}", nombre)
            .replace("{PROMPT}", json.dumps(prompt)[1:-1])
            .replace("{SEED}", str(seed))
        )
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
    {PROMPT}, {SEED} y {FRAMES} en cualquier valor de sus nodos. {SEED} y
    {FRAMES} se sustituyen sin comillas, así que van como valor numérico.
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
        crudo = wf_path.read_text()
        wf = json.loads(
            crudo.replace("{IMAGE}", nombre)
            .replace("{PROMPT}", json.dumps(prompt)[1:-1])
            .replace("{SEED}", str(seed))
            .replace("{FRAMES}", str(I2V_FRAMES))
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
    audio (SaveAudio / SaveAudioMP3). {SEED} y {DURACION} van como valor numérico
    (sin comillas); {TAGS} y {LYRICS} escapados para vivir dentro del JSON.
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
        crudo = wf_path.read_text()
        wf = json.loads(
            crudo.replace("{TAGS}", json.dumps(tags)[1:-1])
            .replace("{LYRICS}", json.dumps(lyrics)[1:-1])
            .replace("{SEED}", str(seed))
            .replace("{DURACION}", str(duracion_s))
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
