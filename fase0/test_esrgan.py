"""Fase 0: upscale con RealESRGAN_x4plus vía ComfyUI — mide seg/imagen."""
import json
import shutil
import sys
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
SRC = "/Users/juanko.dev/Documents/ComfyUI/ComfyUI/output/loomcast_fase0_00001_.png"
INPUT_DIR = "/Users/juanko.dev/Documents/ComfyUI/ComfyUI/input"

WF = {
    "load": {"class_type": "LoadImage", "inputs": {"image": "fase0_upscale_src.png"}},
    "model": {
        "class_type": "UpscaleModelLoader",
        "inputs": {"model_name": "RealESRGAN_x4plus.pth"},
    },
    "upscale": {
        "class_type": "ImageUpscaleWithModel",
        "inputs": {"upscale_model": ["model", 0], "image": ["load", 0]},
    },
    "save": {
        "class_type": "SaveImage",
        "inputs": {"images": ["upscale", 0], "filename_prefix": "loomcast_fase0_up"},
    },
}

shutil.copy(SRC, f"{INPUT_DIR}/fase0_upscale_src.png")

req = urllib.request.Request(
    f"{COMFY}/prompt",
    data=json.dumps({"prompt": WF}).encode(),
    headers={"Content-Type": "application/json"},
)
t0 = time.time()
with urllib.request.urlopen(req) as r:
    pid = json.load(r)["prompt_id"]

while True:
    with urllib.request.urlopen(f"{COMFY}/history/{pid}") as r:
        hist = json.load(r)
    if pid in hist:
        st = hist[pid].get("status", {})
        if st.get("status_str") == "error":
            print(json.dumps(hist[pid], indent=2)[:2000])
            sys.exit("ERROR")
        if st.get("completed"):
            break
    if time.time() - t0 > 600:
        sys.exit("TIMEOUT")
    time.sleep(1)

print(f"Upscale 768x1344 -> 3072x5376 en {time.time() - t0:.1f}s")
