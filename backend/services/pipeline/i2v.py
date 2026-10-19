"""Etapa i2v — image-to-video: movimiento generado por IA + RIFE.

Por cada escena: anima la imagen con el workflow i2v (ComfyUI) —que produce un
clip corto, de unos pocos cuadros— y lo estira con RIFE hasta la duración de su
segmento de voz, generando los cuadros que esa duración pide a fps_final.
Escribe en clips/, de modo que el armado con movimiento (concat + subtítulos +
voz) funcione igual que en el modo Ken Burns.
"""
import time
import tempfile
from pathlib import Path

from ... import parada, procesos
from ...clients import comfy, rife
from ...config import I2V_FPS_FINAL, PROYECTOS_DIR, motor_i2v
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo
from .. import progreso
from ._ffmpeg import args_video, duracion, sin_restos
from .clips import ALTO, ANCHO, pendientes_de_modo


def clip_i2v(imagen: Path, prompt: str, seed: int, dur: float, salida: Path,
             motor: str | None = None) -> None:
    """Anima `imagen` con el motor i2v elegido y deja el clip listo para el
    montaje. `motor` es un id de [i2v.motores]; None usa [i2v].motor."""
    m = motor_i2v(motor)
    with tempfile.TemporaryDirectory() as tmp:
        crudo, suave = Path(tmp) / "crudo.mp4", Path(tmp) / "suave.mp4"
        comfy.generar_video_i2v(imagen, prompt, seed, crudo, motor=m.id)

        # El clip i2v es corto (pocos cuadros) y hay que estirarlo hasta la
        # duración de la escena: se le piden a RIFE los cuadros que esa duración
        # necesita, en vez de un múltiplo de los fps. Con el factor por fps
        # quedarían pocos cuadros distintos repetidos muchas veces y el
        # movimiento saldría a tirones.
        frames = max(2, round(dur * I2V_FPS_FINAL))
        rife.interpolar(crudo, suave, m.fps_origen, I2V_FPS_FINAL, frames)

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
        procesos.ejecutar(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(suave),
             "-vf", f"setpts={factor:.5f}*PTS,fps=60,{escalar}",
             "-an", *args_video(), str(salida)],
            timeout=procesos.CLIP_S, que="ffmpeg (clip i2v)", check=True,
        )


def generar_i2v(proyecto_id: int, forzar: bool = False,
                motor: str | None = None) -> str:
    """Genera un clip animado por escena.

    Reanudable: se saltan las escenas que ya tienen un clip hecho en modo i2v,
    para que un corte a mitad (suspensión, timeout de ComfyUI) no obligue a
    repetir lo ya hecho. Un clip de otro modo sí se rehace: si no, cambiar a
    i2v armaría el video con los clips del modo anterior. Con `forzar` se
    regeneran todas, que es lo que hace falta tras cambiar los prompts.
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
             "seed": e.seed, "dur": e.t_fin - e.t_inicio,
             "clip_modo": e.clip_modo, "clip_motor": e.clip_motor}
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

    m = motor_i2v(motor)
    pendientes = pendientes_de_modo(clips_dir, escenas, "i2v", forzar, motor=m.id)
    saltadas = len(escenas) - len(pendientes)
    if not pendientes:
        return f"{len(escenas)} clips i2v ya estaban generados (nada que hacer)"

    try:
        for i, e in enumerate(pendientes):
            # Entre escena y escena, que es lo que hace que parar un lote de
            # doce no tire por la borda los clips ya animados.
            parada.comprobar(f"quedaban {len(pendientes) - i} clips")
            progreso.lote(i, len(pendientes), "clip")
            t0 = time.time()
            salida = clips_dir / f"{e['orden']:02d}.mp4"
            with sin_restos(salida):
                clip_i2v(img_dir / f"{e['orden']:02d}.png", e["prompt"], e["seed"],
                         e["dur"], salida, motor=m.id)
            with get_session() as s:
                escenas_repo.anotar_clip(s, proyecto_id, e["orden"], "i2v",
                                         time.time() - t0, motor=m.id)
                s.commit()
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "CLIPS")
        s.commit()
    reanudado = f" ({saltadas} ya estaban)" if saltadas else ""
    return (f"{len(pendientes)} clips i2v con {m.nombre} + RIFE a "
            f"{I2V_FPS_FINAL}fps{reanudado}")
