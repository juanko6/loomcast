"""Etapa i2v — image-to-video: movimiento generado por IA + RIFE.

Por cada escena: anima la imagen con el workflow i2v (ComfyUI) —que produce un
clip corto, de unos pocos cuadros— y lo estira con RIFE hasta la duración de su
segmento de voz, generando los cuadros que esa duración pide a fps_final.
Escribe en clips/, de modo que el armado con movimiento (concat + subtítulos +
voz) funcione igual que en el modo Ken Burns.
"""
import subprocess
import time
import tempfile
from pathlib import Path

from ...clients import comfy, rife
from ...config import I2V_FPS_FINAL, I2V_FPS_ORIGEN, PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo
from ._ffmpeg import args_video, duracion
from .clips import ALTO, ANCHO


def clip_i2v(imagen: Path, prompt: str, seed: int, dur: float, salida: Path) -> None:
    """Anima `imagen` con el modelo i2v y deja el clip listo para el montaje."""
    with tempfile.TemporaryDirectory() as tmp:
        crudo, suave = Path(tmp) / "crudo.mp4", Path(tmp) / "suave.mp4"
        comfy.generar_video_i2v(imagen, prompt, seed, crudo)

        # El clip i2v es corto (pocos cuadros) y hay que estirarlo hasta la
        # duración de la escena: se le piden a RIFE los cuadros que esa duración
        # necesita, en vez de un múltiplo de los fps. Con el factor por fps
        # quedarían pocos cuadros distintos repetidos muchas veces y el
        # movimiento saldría a tirones.
        frames = max(2, round(dur * I2V_FPS_FINAL))
        rife.interpolar(crudo, suave, I2V_FPS_ORIGEN, I2V_FPS_FINAL, frames)

        # Corrección residual: la duración ya sale casi exacta, esto solo
        # absorbe el redondeo a cuadro entero.
        factor = dur / (duracion(suave) or dur)
        # El modelo i2v genera a su propia resolución (menor que la del
        # montaje), así que hay que llevar el clip a 1080x1920 como los de Ken
        # Burns: el armado superpone subtítulos rasterizados a ese tamaño con
        # overlay=0:0 y, en un clip más pequeño, el texto caería fuera.
        escalar = (
            f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase"
            f":flags=lanczos,crop={ANCHO}:{ALTO}"
        )
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(suave),
             "-vf", f"setpts={factor:.5f}*PTS,fps=60,{escalar}",
             "-an", *args_video(), str(salida)],
            check=True,
        )


def generar_i2v(proyecto_id: int, forzar: bool = False) -> str:
    """Genera un clip animado por escena.

    Reanudable: las escenas que ya tienen su clip se saltan, para que un corte
    a mitad (suspensión, timeout de ComfyUI) no obligue a repetir lo ya hecho.
    Con `forzar` se regeneran todas, que es lo que hace falta tras cambiar los
    prompts de movimiento.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            # El i2v se dirige con el prompt de movimiento; el visual describe
            # una imagen fija y genera clips casi estáticos. Las escenas
            # anteriores a ese campo caen de vuelta al visual.
            {"orden": e.orden, "prompt": e.prompt_movimiento or e.prompt,
             "seed": e.seed, "dur": e.t_fin - e.t_inicio}
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

    pendientes = escenas if forzar else [
        e for e in escenas
        if not (clips_dir / f"{e['orden']:02d}.mp4").exists()
    ]
    saltadas = len(escenas) - len(pendientes)
    if not pendientes:
        return f"{len(escenas)} clips i2v ya estaban generados (nada que hacer)"

    try:
        for e in pendientes:
            t0 = time.time()
            clip_i2v(img_dir / f"{e['orden']:02d}.png", e["prompt"], e["seed"],
                     e["dur"], clips_dir / f"{e['orden']:02d}.mp4")
            with get_session() as s:
                escenas_repo.anotar_clip(s, proyecto_id, e["orden"], "i2v",
                                         time.time() - t0)
                s.commit()
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "CLIPS")
        s.commit()
    reanudado = f" ({saltadas} ya estaban)" if saltadas else ""
    return (f"{len(pendientes)} clips i2v (movimiento IA) + RIFE a "
            f"{I2V_FPS_FINAL}fps{reanudado}")
