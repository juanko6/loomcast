"""Etapa 9 — CLIPS: movimiento Ken Burns por escena, nativo a 60fps.

Cada imagen reescalada se convierte en un clip 1080x1920 con un zoom/paneo
lento renderizado directamente a 60fps (suave, sin interpolación). Se alterna
zoom-in / zoom-out por escena para dar variedad al montaje.
"""
import subprocess
import time
from pathlib import Path

from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo
from .. import progreso
from ._ffmpeg import args_video

FPS = 60
ANCHO, ALTO = 1080, 1920
# Lienzo de trabajo 2x: da margen para el zoom sin perder nitidez ni jitter.
TRABAJO = "2160:3840"
INCR = 0.0006      # velocidad del zoom por cuadro
ZOOM_MAX = 1.15


# Tope de un clip. Con `-loop 1` ffmpeg no termina nunca si no consigue decodificar
# la imagen (un PNG corrupto o a medio escribir): reintenta eternamente y el job
# se queda corriendo. Se valida la imagen antes y, por si acaso, se corta aquí.
TIMEOUT_CLIP_S = 900


def _ffmpeg_clip(cmd: list[str], imagen: Path, que: str) -> None:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(imagen) as im:
            im.load()
    except (OSError, UnidentifiedImageError) as e:
        raise RuntimeError(f"ffmpeg {que} no puede leer la imagen {imagen.name}: {e}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_CLIP_S)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ffmpeg {que} no terminó en {TIMEOUT_CLIP_S} s con {imagen.name}; "
            "se cancela para no dejar el job colgado"
        )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg {que} falló: {r.stderr[-500:]}")


def _ken_burns_vf(orden: int, frames: int) -> str:
    if orden % 2 == 0:
        z = f"min(zoom+{INCR},{ZOOM_MAX})"                       # zoom in
    else:
        z = f"if(eq(on,0),{ZOOM_MAX},max(zoom-{INCR},1.0))"      # zoom out
    return (
        f"scale={TRABAJO}:force_original_aspect_ratio=increase,crop={TRABAJO},"
        f"zoompan=z='{z}':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={ANCHO}x{ALTO}:fps={FPS}"
    )


def pendientes_de_modo(clips_dir: Path, escenas: list[dict], modo: str,
                       forzar: bool = False) -> list[dict]:
    """Escenas cuyo clip hay que (re)generar para el modo pedido.

    Hace falta si no existe el archivo o si el que hay se hizo con otro modo:
    así una tanda cortada a medias se reanuda, pero cambiar de modo nunca deja
    el video armado con clips del modo anterior. Los clips anteriores al
    registro de `clip_modo` cuentan como desconocidos y se rehacen.
    """
    if forzar:
        return list(escenas)
    return [
        e for e in escenas
        if not (clips_dir / f"{e['orden']:02d}.mp4").exists()
        or e.get("clip_modo") != modo
    ]


def clip_ken_burns(imagen: Path, orden: int, dur: float, salida: Path) -> None:
    """Un clip con zoom/paneo lento sobre `imagen`, de `dur` segundos."""
    frames = max(1, round(dur * FPS))
    _ffmpeg_clip(
        ["ffmpeg", "-loglevel", "error", "-y",
         "-loop", "1", "-i", str(imagen),
         "-vf", _ken_burns_vf(orden, frames),
         "-frames:v", str(frames),
         *args_video(), str(salida)],
        imagen, f"(escena {orden})",
    )


def clip_estatico(imagen: Path, dur: float, salida: Path) -> None:
    """Un clip de imagen fija, del mismo tamaño y fps que los demás modos, para
    que el armado pueda concatenarlo junto a clips con movimiento."""
    frames = max(1, round(dur * FPS))
    _ffmpeg_clip(
        ["ffmpeg", "-loglevel", "error", "-y",
         "-loop", "1", "-i", str(imagen),
         "-vf", (f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase"
                 f":flags=lanczos,crop={ANCHO}:{ALTO},fps={FPS}"),
         "-frames:v", str(frames),
         *args_video(), str(salida)],
        imagen, "estático",
    )


def generar_clips(proyecto_id: int, forzar: bool = False) -> str:
    """Clip Ken Burns por escena. Salta las que ya tengan uno hecho con este
    mismo modo, de modo que reanudar una tanda no rehaga lo ya generado."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            {"orden": e.orden, "dur": e.t_fin - e.t_inicio,
             "clip_modo": e.clip_modo}
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]
        slug = p.slug

    if not escenas:
        raise ValueError("El proyecto no tiene escenas")

    base = PROYECTOS_DIR / slug
    up_dir = base / "upscale"
    clips_dir = base / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    faltantes = [e["orden"] for e in escenas
                 if not (up_dir / f"{e['orden']:02d}.png").exists()]
    if faltantes:
        raise ValueError(f"Faltan imágenes reescaladas de las escenas {faltantes}")

    pendientes = pendientes_de_modo(clips_dir, escenas, "kenburns", forzar)
    if not pendientes:
        return f"Los {len(escenas)} clips Ken Burns ya estaban hechos"

    for i, e in enumerate(pendientes):
        progreso.lote(i, len(pendientes), "clip")
        t0 = time.time()
        clip_ken_burns(up_dir / f"{e['orden']:02d}.png", e["orden"], e["dur"],
                       clips_dir / f"{e['orden']:02d}.mp4")
        with get_session() as s:
            escenas_repo.anotar_clip(s, proyecto_id, e["orden"], "kenburns",
                                     time.time() - t0)
            s.commit()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "CLIPS")
        s.commit()
    saltadas = len(escenas) - len(pendientes)
    reanudado = f" ({saltadas} ya estaban)" if saltadas else ""
    return f"{len(pendientes)} clips Ken Burns a {FPS}fps{reanudado}"
