"""Etapa i2v — image-to-video: movimiento generado por IA + RIFE.

Por cada escena: anima la imagen con el workflow i2v (ComfyUI), interpola con
RIFE a fps_final y ajusta la velocidad para que el clip dure exactamente lo que
su segmento de voz. Escribe en clips/, de modo que el armado con movimiento
(concat + subtítulos + voz) funcione igual que en el modo Ken Burns.
"""
import subprocess
import tempfile
from pathlib import Path

from ...clients import comfy, rife
from ...config import I2V_FPS_FINAL, I2V_FPS_ORIGEN, PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo
from ._ffmpeg import args_video


def _duracion(mp4: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(mp4)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or 0)


def generar_i2v(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            {"orden": e.orden, "prompt": e.prompt, "seed": e.seed,
             "dur": e.t_fin - e.t_inicio}
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]
        slug = p.slug

    if not escenas:
        raise ValueError("El proyecto no tiene escenas")

    base = PROYECTOS_DIR / slug
    img_dir = base / "imagenes"
    clips_dir = base / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    faltantes = [e["orden"] for e in escenas
                 if not (img_dir / f"{e['orden']:02d}.png").exists()]
    if faltantes:
        raise ValueError(f"Faltan imágenes de las escenas {faltantes}")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            for e in escenas:
                crudo = Path(tmp) / f"crudo_{e['orden']:02d}.mp4"
                suave = Path(tmp) / f"suave_{e['orden']:02d}.mp4"
                comfy.generar_video_i2v(
                    img_dir / f"{e['orden']:02d}.png", e["prompt"], e["seed"], crudo
                )
                rife.interpolar(crudo, suave, I2V_FPS_ORIGEN, I2V_FPS_FINAL)

                # Ajustar velocidad para que el clip dure lo que su escena
                d = _duracion(suave) or e["dur"]
                factor = e["dur"] / d
                subprocess.run(
                    ["ffmpeg", "-loglevel", "error", "-y", "-i", str(suave),
                     "-vf", f"setpts={factor:.5f}*PTS,fps=60",
                     "-an", *args_video(), str(clips_dir / f"{e['orden']:02d}.mp4")],
                    check=True,
                )
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "CLIPS")
        s.commit()
    return f"{len(escenas)} clips i2v (movimiento IA) + RIFE a {I2V_FPS_FINAL}fps"
