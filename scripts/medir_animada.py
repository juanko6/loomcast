"""Mide en esta máquina lo que cuesta una imagen animada en bucle con LTX-2.5.

Es el banco del modo «Animada» de la galería: lanza `workflows/loop_ltx25_api.json`
a mano, sin backend ni cola, y deja en una carpeta los clips y un resumen con lo
que decide los valores de `[animada]` en config.toml:

  - tiempo de cada render y GiB que se fueron al swap (Swapouts, no Pageouts);
  - la calidad del empalme: cuánto se mueve el clip de un cuadro al siguiente,
    cuánto salta al volver del penúltimo cuadro al primero (el último se quita
    porque es copia del primero), si hay un tirón de vuelta en los últimos
    segundos y si la guía final congela el final;
  - el escalado: Real-ESRGAN x4plus por ComfyUI contra `realesrgan-ncnn-vulkan`
    (realesr-animevideov3), en segundos por cuadro.

Se corre desde la raíz del repo con ComfyUI levantado (--gpu-only) y sin el LLM
grande cargado:

    .venv/bin/python scripts/medir_animada.py --salida /tmp/animada \\
        --prompt-imagen "un personaje groovy..." --prompt-movimiento "..." \\
        --frames 121 161 --fps 12 --ancho 480 --alto 864 --escalado 24
"""
import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import memoria  # noqa: E402
from backend.clients import comfy, rife  # noqa: E402
from backend.config import ROOT  # noqa: E402

WORKFLOW = ROOT / "workflows" / "loop_ltx25_api.json"
REALESRGAN = ROOT / "tools" / "realesrgan-ncnn-vulkan-20220424-macos" / "realesrgan-ncnn-vulkan"


def _swap() -> float:
    return memoria.swapouts_gb() or 0.0


def render_loop(imagen: Path, prompt: str, seed: int, frames: int, fps: int,
                ancho: int, alto: int, destino: Path, guia: float) -> None:
    wf_crudo = WORKFLOW.read_text()
    with httpx.Client(timeout=30) as c:
        nombre = comfy._subir_imagen(c, imagen)
        wf = comfy._render(wf_crudo, IMAGE=nombre, PROMPT=prompt, SEED=seed,
                           FRAMES=frames, FPS=fps, WIDTH=ancho, HEIGHT=alto)
        wf["398:420"]["inputs"]["strength"] = guia
        entry = comfy._encolar_y_esperar(c, wf)
        comfy._descargar_primer_video(c, entry, destino)


def cuadros_gris(video: Path, w: int = 135, h: int = 240) -> np.ndarray:
    """Los cuadros del clip en gris y pequeños, como array (n, h, w) float."""
    crudo = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(video),
         "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
        stdin=subprocess.DEVNULL, capture_output=True, check=True,
    ).stdout
    return np.frombuffer(crudo, np.uint8).reshape(-1, h, w).astype(np.float32)


def empalme(video: Path, fps: int) -> dict:
    """Métricas del bucle: el salto al volver al principio contra el paso típico.

    Todo en diferencia absoluta media de gris (0–255) entre dos cuadros.
    """
    f = cuadros_gris(video)
    pasos = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    tipico = float(np.median(pasos))
    ultimo_vs_primero = float(np.abs(f[-1] - f[0]).mean())
    # El bucle real: se quita el último (copia del primero) y del penúltimo se
    # vuelve al primero.
    salto = float(np.abs(f[-2] - f[0]).mean())
    cola = pasos[-2 * fps:]
    final = pasos[-fps:]
    return {
        "cuadros": int(len(f)),
        "paso_tipico": round(tipico, 3),
        "ultimo_vs_primero": round(ultimo_vs_primero, 3),
        "salto_bucle": round(salto, 3),
        "salto_en_pasos": round(salto / tipico, 2) if tipico else None,
        # Un tirón de vuelta al cerrar: el paso más grande de los 2 últimos
        # segundos contra el típico.
        "tiron_cola_en_pasos": round(float(cola.max()) / tipico, 2) if tipico else None,
        # Congelado: el último segundo se mueve mucho menos que el resto.
        "movimiento_ultimo_s_en_pasos": round(float(final.mean()) / tipico, 2) if tipico else None,
        "movimiento_medio_s": [round(float(x), 3) for x in
                               pasos[: len(pasos) // fps * fps].reshape(-1, fps).mean(axis=1)],
    }


def interpolar(entrada: Path, salida: Path, fps: int, fps_final: int) -> float:
    """RIFE al fps final con (n-1)·k+1 cuadros: el último sigue siendo el primero."""
    n = len(cuadros_gris(entrada, 16, 16))
    k = fps_final // fps
    t = time.monotonic()
    rife.interpolar(entrada, salida, fps, fps_final, frames=(n - 1) * k + 1)
    return time.monotonic() - t


def escalar_comfy(video: Path, carpeta: Path, n: int) -> float:
    """ESRGAN x4plus por ComfyUI, cuadro a cuadro; devuelve s/cuadro en caliente."""
    carpeta.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
                    "-frames:v", str(n + 1), str(carpeta / "in_%04d.png")],
                   stdin=subprocess.DEVNULL, check=True)
    entradas = sorted(carpeta.glob("in_*.png"))
    # El primero carga el modelo: fuera de la media.
    comfy.upscale_imagen(entradas[0], carpeta / "out_0000.png")
    t = time.monotonic()
    for i, e in enumerate(entradas[1:], 1):
        comfy.upscale_imagen(e, carpeta / f"out_{i:04d}.png")
    return (time.monotonic() - t) / max(1, len(entradas) - 1)


def escalar_ncnn(video: Path, carpeta: Path, n: int, modelo: str) -> float | None:
    if not REALESRGAN.exists():
        return None
    din, dout = carpeta / "in", carpeta / "out"
    din.mkdir(parents=True, exist_ok=True)
    dout.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
                    "-frames:v", str(n), str(din / "%04d.png")],
                   stdin=subprocess.DEVNULL, check=True)
    t = time.monotonic()
    subprocess.run([str(REALESRGAN), "-i", str(din), "-o", str(dout), "-n", modelo,
                    "-s", "4", "-f", "png", "-m", str(REALESRGAN.parent / "models")],
                   stdin=subprocess.DEVNULL, capture_output=True, check=True)
    return (time.monotonic() - t) / n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--imagen", type=Path, help="imagen de partida; si no, se genera")
    ap.add_argument("--prompt-imagen", default="")
    ap.add_argument("--prompt-movimiento", required=True)
    ap.add_argument("--frames", type=int, nargs="+", default=[121, 161])
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--fps-final", type=int, default=24)
    ap.add_argument("--ancho", type=int, default=480)
    ap.add_argument("--alto", type=int, default=864)
    ap.add_argument("--guia", type=float, default=1.0, help="strength de la guía final")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--escalado", type=int, default=0,
                    help="cuadros con los que comparar los escaladores (0 = no)")
    a = ap.parse_args()

    a.salida.mkdir(parents=True, exist_ok=True)
    seed = a.seed if a.seed is not None else random.randint(1, 2**31)
    res: dict = {"seed": seed, "fps": a.fps, "ancho": a.ancho, "alto": a.alto,
                 "guia": a.guia, "renders": []}

    imagen = a.imagen
    if imagen is None:
        imagen = a.salida / "imagen.png"
        t = time.monotonic()
        comfy.generar_imagen(a.prompt_imagen, seed, imagen, 768, 1344)
        res["imagen_s"] = round(time.monotonic() - t, 1)
        print(f"imagen: {res['imagen_s']} s", flush=True)
    print(comfy.liberar_memoria(hasta_gb=28), flush=True)

    for frames in a.frames:
        destino = a.salida / f"loop_{frames}.mp4"
        swap0, libre0 = _swap(), memoria.disponible_gb()
        t = time.monotonic()
        render_loop(imagen, a.prompt_movimiento, seed, frames, a.fps,
                    a.ancho, a.alto, destino, a.guia)
        dur = time.monotonic() - t
        r = {"frames": frames, "segundos_clip": round((frames - 1) / a.fps, 2),
             "render_s": round(dur, 1), "swapouts_gb": round(_swap() - swap0, 2),
             "libre_antes_gb": round(libre0 or 0, 1),
             "empalme": empalme(destino, a.fps)}
        interp = a.salida / f"loop_{frames}_{a.fps_final}.mp4"
        r["rife_s"] = round(interpolar(destino, interp, a.fps, a.fps_final), 1)
        r["empalme_rife"] = empalme(interp, a.fps_final)
        res["renders"].append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)

    print(comfy.liberar_memoria(hasta_gb=28), flush=True)
    if a.escalado:
        base = a.salida / f"loop_{a.frames[0]}.mp4"
        swap0 = _swap()
        res["esrgan_comfy_s_cuadro"] = round(escalar_comfy(base, a.salida / "esc_comfy", a.escalado), 2)
        res["esrgan_comfy_swap_gb"] = round(_swap() - swap0, 2)
        comfy.liberar_memoria()
        for modelo in ("realesr-animevideov3-x4", "realesrgan-x4plus"):
            try:
                s = escalar_ncnn(base, a.salida / f"esc_{modelo}", a.escalado, modelo)
            except (subprocess.CalledProcessError, OSError) as e:
                s = f"falló: {e}"
            res[f"ncnn_{modelo}_s_cuadro"] = round(s, 2) if isinstance(s, float) else s
        print(json.dumps({k: v for k, v in res.items() if "cuadro" in k}), flush=True)

    (a.salida / "resumen.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"resumen en {a.salida / 'resumen.json'}")


if __name__ == "__main__":
    main()
