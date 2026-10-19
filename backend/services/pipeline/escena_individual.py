"""Regeneración de una sola escena, en el modo que se elija.

Los tres modos escriben el clip en clips/NN.mp4 con el mismo formato
(1080x1920 a 60fps), así que el armado los concatena sin saber de dónde salió
cada uno y un mismo video puede mezclarlos.
"""
import time

from ...config import PROYECTOS_DIR, motor_i2v
from ...db import get_session
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo
from ... import parada
from .. import progreso
from . import clips as clips_mod
from . import i2v as i2v_mod
from ._ffmpeg import sin_restos

MODOS = ("estatico", "kenburns", "i2v")


def _imagen_para(base, orden: int, preferir_upscale: bool):
    """Ken Burns y el estático se ven mejor sobre la imagen reescalada; si no
    se ha pasado por ESRGAN se usa la original en vez de fallar."""
    if preferir_upscale:
        up = base / "upscale" / f"{orden:02d}.png"
        if up.exists():
            return up
    img = base / "imagenes" / f"{orden:02d}.png"
    if not img.exists():
        raise ValueError(f"La escena {orden} no tiene imagen generada")
    return img


def generar_clips_mixto(proyecto_id: int, motor: str = "") -> str:
    """Genera todos los clips respetando el modo elegido en cada escena.

    Es el 'generar todo' cuando el video mezcla modos: las escenas sin modo
    propio caen a Ken Burns. Reanudable como el resto: salta las que ya tienen
    su clip hecho con el modo que les toca.

    `motor` es el motor i2v para las escenas que vayan en ese modo; las demás lo
    ignoran.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [(e.orden, e.modo or "kenburns", e.clip_modo, e.clip_motor)
                   for e in escenas_repo.por_proyecto(s, proyecto_id)]
        slug = p.slug

    clips_dir = PROYECTOS_DIR / slug / "clips"
    # Se resuelve antes qué hay que rehacer para poder contar el lote sobre el
    # trabajo real: si el total fuese el de escenas, una tanda reanudada
    # empezaría la barra a media altura.
    # Una escena i2v también se rehace si se pide con otro motor que el que
    # tiene su clip, igual que si se cambiara de modo.
    quiere = motor_i2v(motor or None).id
    pendientes = [
        (orden, modo)
        for orden, modo, clip_modo, clip_motor in escenas
        if not ((clips_dir / f"{orden:02d}.mp4").exists() and clip_modo == modo
                and (modo != "i2v" or clip_motor == quiere))
    ]
    hechas, cuenta = len(escenas) - len(pendientes), {}
    for i, (orden, modo) in enumerate(pendientes):
        parada.comprobar(f"quedaban {len(pendientes) - i} clips")
        progreso.lote(i, len(pendientes), "clip")
        regenerar_clip(proyecto_id, orden, modo, motor=motor)
        cuenta[modo] = cuenta.get(modo, 0) + 1

    if not cuenta:
        return f"Los {hechas} clips ya estaban al día (nada que hacer)"
    detalle = ", ".join(f"{n} {m}" for m, n in sorted(cuenta.items()))
    saltadas = f" ({hechas} ya estaban)" if hechas else ""
    return f"Clips generados: {detalle}{saltadas}"


def regenerar_clip(proyecto_id: int, orden: int, modo: str = "",
                   motor: str = "") -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        e = next(
            (x for x in escenas_repo.por_proyecto(s, proyecto_id) if x.orden == orden),
            None,
        )
        if e is None:
            raise ValueError(f"El proyecto no tiene escena {orden}")
        # El modo del job manda; si no viene, el guardado en la escena.
        modo = modo or e.modo or "kenburns"
        if modo not in MODOS:
            raise ValueError(f"Modo desconocido: {modo} (usa {', '.join(MODOS)})")
        datos = {"prompt": e.prompt_movimiento or e.prompt, "seed": e.seed,
                 "dur": e.t_fin - e.t_inicio}
        slug = p.slug

    base = PROYECTOS_DIR / slug
    clips_dir = base / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    salida = clips_dir / f"{orden:02d}.mp4"

    t0 = time.time()
    # El motor solo tiene sentido en i2v; en los otros modos queda vacío para no
    # dejar en la escena el rastro de un motor que no se ha usado.
    motor_usado = ""
    # El clip anterior de esta escena ya no vale (se pidió rehacerlo), así que
    # si la generación se corta no puede quedar el nuevo a medio escribir.
    with sin_restos(salida):
        if modo == "i2v":
            motor_usado = motor_i2v(motor or None).id
            try:
                i2v_mod.clip_i2v(_imagen_para(base, orden, False), datos["prompt"],
                                 datos["seed"], datos["dur"], salida,
                                 motor=motor_usado)
            finally:
                from ...clients import comfy
                comfy.liberar_memoria()
        elif modo == "kenburns":
            clips_mod.clip_ken_burns(_imagen_para(base, orden, True), orden,
                                     datos["dur"], salida)
        else:
            clips_mod.clip_estatico(_imagen_para(base, orden, True), datos["dur"],
                                    salida)
    tardo = time.time() - t0

    with get_session() as s:
        for x in escenas_repo.por_proyecto(s, proyecto_id):
            if x.orden == orden:
                x.clip_modo, x.clip_s, x.modo = modo, round(tardo, 1), modo
                x.clip_motor = motor_usado
        s.commit()
    con = f" con {motor_i2v(motor_usado).nombre}" if motor_usado else ""
    return (f"Clip de la escena {orden + 1} regenerado en modo {modo}"
            f"{con} ({tardo:.0f}s)")
