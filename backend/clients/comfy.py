"""Adaptador de ComfyUI: encola workflows, espera el resultado y descarga
la imagen. El workflow base vive en workflows/z_image_turbo_api.json."""
import json
import time
from pathlib import Path

import httpx

from ..config import COMFY_URL, ROOT

WORKFLOW_ZIMAGE = ROOT / "workflows" / "z_image_turbo_api.json"
TIMEOUT_IMAGEN_S = 600


class ComfyError(RuntimeError):
    pass


def _cargar_workflow(prompt: str, seed: int) -> dict:
    wf = json.loads(WORKFLOW_ZIMAGE.read_text())
    wf["positive"]["inputs"]["text"] = prompt
    wf["sampler"]["inputs"]["seed"] = seed
    return wf


def generar_imagen(prompt: str, seed: int, destino: Path) -> None:
    """Genera una imagen con Z-Image-Turbo y la guarda en `destino`."""
    with httpx.Client(timeout=30) as c:
        r = c.post(f"{COMFY_URL}/prompt", json={"prompt": _cargar_workflow(prompt, seed)})
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
                    break
            if time.time() - inicio > TIMEOUT_IMAGEN_S:
                raise ComfyError(f"Timeout generando imagen (prompt {pid})")
            time.sleep(2)

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
