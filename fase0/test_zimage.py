"""Fase 0: mide seg/imagen de Z-Image-Turbo vía la API de ComfyUI (MPS)."""
import json
import sys
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
WORKFLOW = "/Users/juanko.dev/Documents/loomcast/workflows/z_image_turbo_api.json"

PROMPT = (
    "Ancient Mayan pyramid at golden hour, dramatic low-angle shot, "
    "lush jungle surrounding it, volumetric god rays, cinematic lighting, "
    "hyperdetailed, vertical composition"
)


def queue(workflow: dict) -> str:
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": workflow}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)["prompt_id"]


def wait(prompt_id: str, timeout: float = 1800) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        with urllib.request.urlopen(f"{COMFY}/history/{prompt_id}") as r:
            hist = json.load(r)
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                print(json.dumps(entry, indent=2)[:3000])
                sys.exit("ERROR en el workflow")
            if status.get("completed"):
                return entry
        time.sleep(1)
    sys.exit("TIMEOUT")


def run(seed: int, label: str) -> float:
    with open(WORKFLOW) as f:
        wf = json.load(f)
    wf["positive"]["inputs"]["text"] = PROMPT
    wf["sampler"]["inputs"]["seed"] = seed
    t0 = time.time()
    entry = wait(queue(wf))
    dt = time.time() - t0
    images = [
        f"{o['filename']}"
        for out in entry.get("outputs", {}).values()
        for o in out.get("images", [])
    ]
    print(f"{label}: {dt:.1f}s -> {images}")
    return dt


if __name__ == "__main__":
    print("Corrida 1 (fría: incluye carga de modelos a memoria)...")
    cold = run(seed=42, label="fría")
    print("Corrida 2 (caliente: modelos ya cargados)...")
    warm1 = run(seed=43, label="caliente 1")
    warm2 = run(seed=44, label="caliente 2")
    print(f"\nRESUMEN: fría={cold:.1f}s | caliente={(warm1 + warm2) / 2:.1f}s promedio")
