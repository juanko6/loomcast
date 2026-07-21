"""Adaptador de ComfyUI: encola workflows, espera el resultado y descarga
imágenes. Los workflows base viven en workflows/*.json."""
import json
import time
from pathlib import Path

import httpx

from ..config import COMFY_URL, I2V_WORKFLOW, ROOT

WORKFLOW_ZIMAGE = ROOT / "workflows" / "z_image_turbo_api.json"
WORKFLOW_ESRGAN = ROOT / "workflows" / "esrgan_api.json"
TIMEOUT_S = 600
EXT_VIDEO = (".mp4", ".webm", ".mkv", ".mov", ".gif")


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


def generar_imagen(prompt: str, seed: int, destino: Path) -> None:
    """Genera una imagen con Z-Image-Turbo y la guarda en `destino`."""
    wf = json.loads(WORKFLOW_ZIMAGE.read_text())
    wf["positive"]["inputs"]["text"] = prompt
    wf["sampler"]["inputs"]["seed"] = seed
    with httpx.Client(timeout=30) as c:
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
    {PROMPT} y {SEED} en cualquier valor de texto de sus nodos.
    """
    wf_path = ROOT / I2V_WORKFLOW
    if not wf_path.exists():
        raise ComfyError(
            f"No existe el workflow i2v en {wf_path}. Exporta tu workflow de "
            "ComfyUI en formato API con los placeholders {IMAGE}, {PROMPT} y "
            "{SEED}, y ponlo en esa ruta (o ajusta config.toml [i2v].workflow)."
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
        _descargar_primer_video(c, entry, destino)


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
