"""Imagen animada en bucle: la preview elegida se mueve y vuelve a sí misma.

Hasta elegir preview es la galería de siempre (`imagen_libre`). A partir de ahí,
tres etapas disparadas por el usuario:

  1. mejorar_movimiento — opcional: el LLM pule el prompt de movimiento que
     escribió el usuario y recomienda la duración.
  2. animar  — LTX-2.5 con la imagen como guía en el primer cuadro y en el
     último, a resolución baja y fps de condicionamiento bajo; RIFE lo lleva al
     fps final y se quita el último cuadro, que es copia del primero.
  3. escalar — Real-ESRGAN x4 cuadro a cuadro y lanczos al tamaño exacto de
     2K o 4K.
"""
import random
import shutil
import tempfile
from pathlib import Path

from ... import parada, procesos
from ...clients import comfy, escalador, llm, rife
from ...config import (
    ANIMADA_CRF,
    ANIMADA_DURACION_MAX_S,
    ANIMADA_DURACION_MIN_S,
    ANIMADA_FPS_FINAL,
    ANIMADA_FPS_ORIGEN,
    ANIMADA_FUNDIDO,
    ANIMADA_LADO_LARGO,
    PROMPTS_DIR,
)
from ...db import get_session
from ...repositories import galeria as galeria_repo
from ...schemas import AnimadaMovimientoLLM
from .. import progreso
from ._ffmpeg import args_video, sin_restos
from .imagen_libre import carpeta, ruta_final, ruta_preview

# Lado largo de cada escala. El corto sale de la proporción de la imagen: en
# 9:16, 1440×2560 y 2160×3840.
LADO_ESCALA = {"2k": 2560, "4k": 3840}


def ruta_video(imagen_id: int, escala: str | None = None) -> Path:
    nombre = f"loop_{escala}.mp4" if escala else "loop.mp4"
    return carpeta(imagen_id) / nombre


def acotar_duracion(segundos: float) -> int:
    return max(ANIMADA_DURACION_MIN_S, min(ANIMADA_DURACION_MAX_S, round(segundos)))


def cuadros_para(duracion_s: float) -> int:
    """Cuadros que se le piden a LTX: 8n+1, lo más cerca de la duración al fps
    de condicionamiento."""
    n = max(1, round(duracion_s * ANIMADA_FPS_ORIGEN / 8))
    return 8 * n + 1


def tamano_generacion(width: int, height: int) -> tuple[int, int]:
    """Tamaño al que anima LTX: el lado largo de config y el corto en
    proporción, los dos múltiplos de 32 como quiere su VAE."""
    escala = ANIMADA_LADO_LARGO / max(width, height)
    w = max(32, round(width * escala / 32) * 32)
    h = max(32, round(height * escala / 32) * 32)
    return w, h


def tamano_escala(width: int, height: int, escala: str) -> tuple[int, int]:
    """Tamaño final de la versión escalada, pares para yuv420p."""
    largo = LADO_ESCALA[escala]
    f = largo / max(width, height)
    return round(width * f / 2) * 2, round(height * f / 2) * 2


def pesos_fundido(fundido: int) -> list[float]:
    """Peso del primer cuadro en cada uno de los `fundido` finales.

    Llega a fundido/(fundido+1), no a 1: el cuadro que viene detrás al dar la
    vuelta es el primero, y repetirlo sería otro tirón.
    """
    return [(i + 1) / (fundido + 1) for i in range(fundido)]


def cerrar_bucle(entrada: Path, salida: Path, cuadros: int, fundido: int,
                 w: int, h: int, fps: int = ANIMADA_FPS_FINAL) -> None:
    """Escribe los `cuadros` primeros de `entrada` (de `w`×`h`) —el último,
    copia del primero, se queda fuera— fundiendo los `fundido` finales hacia el
    primero.

    La guía final de LTX deja la pose donde empezó, pero no el cuadro idéntico:
    el VAE devuelve la textura con un brillo algo distinto (medido: 1,6 niveles
    de media y hasta 9 en los bordes, cuatro veces el paso entre dos cuadros), y
    al volver al principio se ve un parpadeo. El fundido lo reparte entre los
    últimos cuadros, que de todas formas casi no se mueven.

    Cómo, y por qué así:
      - la mezcla se hace con numpy sobre los pocos cuadros de la cola, no con
        el `blend` de ffmpeg: ese sincroniza sus dos entradas por marca de
        tiempo y, medido, aplicaba los pesos desplazados;
      - en yuv420p crudo, sin pasar por RGB: la ida y vuelta de color y croma
        dejaba los cuadros mezclados 0,3 niveles por debajo de los demás, otro
        escalón justo donde empieza el fundido.
    """
    import numpy as np

    fundido = max(0, min(fundido, cuadros - 1))
    desde = cuadros - fundido
    tam = w * h * 3 // 2
    with tempfile.TemporaryDirectory() as tmp:
        if fundido:
            cola, mezcla = Path(tmp) / "cola.yuv", Path(tmp) / "mezcla.yuv"
            # El primero y los de la cola, en ese orden.
            seleccion = f"eq(n\\,0)+between(n\\,{desde}\\,{cuadros - 1})"
            procesos.ejecutar(
                ["ffmpeg", "-loglevel", "error", "-y", "-i", str(entrada),
                 "-vf", f"select={seleccion}", "-fps_mode", "passthrough",
                 "-f", "rawvideo", "-pix_fmt", "yuv420p", str(cola)],
                timeout=procesos.CLIP_S, que="ffmpeg (cola del bucle)", check=True,
            )
            crudo = np.fromfile(cola, np.uint8)
            if crudo.size != tam * (fundido + 1):
                raise RuntimeError(
                    f"La cola del bucle tiene {crudo.size / tam:.1f} cuadros de "
                    f"{w}×{h} y se esperaban {fundido + 1}"
                )
            cs = crudo.reshape(fundido + 1, tam).astype(np.float32)
            pesos = np.array(pesos_fundido(fundido), np.float32)[:, None]
            mezclados = cs[1:] * (1 - pesos) + cs[0] * pesos
            mezclados.round().clip(0, 255).astype(np.uint8).tofile(mezcla)
            filtro = (
                f"[0:v]trim=end_frame={desde},setpts=PTS-STARTPTS[cab];"
                f"[1:v]setpts=PTS-STARTPTS[mez];[cab][mez]concat=n=2:v=1[v]"
            )
            entradas = ["-i", str(entrada), "-f", "rawvideo", "-pix_fmt", "yuv420p",
                        "-s", f"{w}x{h}", "-framerate", str(fps), "-i", str(mezcla)]
        else:
            filtro = f"[0:v]trim=end_frame={cuadros},setpts=PTS-STARTPTS[v]"
            entradas = ["-i", str(entrada)]
        procesos.ejecutar(
            ["ffmpeg", "-loglevel", "error", "-y", *entradas,
             "-filter_complex", filtro, "-map", "[v]", "-r", str(fps),
             "-an", *args_video(), "-movflags", "+faststart", str(salida)],
            timeout=procesos.CLIP_S, que="ffmpeg (cerrar el bucle)", check=True,
        )


def _imagen_aprobada(imagen_id: int, indice: int | None) -> Path:
    """La imagen que se anima: la copia de la preview aprobada."""
    final = ruta_final(imagen_id)
    if final.exists():
        return final
    if indice is not None and ruta_preview(imagen_id, indice).exists():
        return ruta_preview(imagen_id, indice)
    raise ValueError("No hay imagen aprobada: elige una preview antes de animar")


def aprobar(imagen_id: int, indice: int) -> None:
    """Aprueba una preview. Sin ESRGAN: el vídeo se anima desde la preview a
    su resolución nativa y lo que se escala, si se pide, es el vídeo."""
    origen = ruta_preview(imagen_id, indice)
    if not origen.exists():
        raise ValueError(f"No existe la preview {indice}")
    shutil.copyfile(origen, ruta_final(imagen_id))
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.set_seed_elegido(s, img, indice)
        s.commit()


def mejorar_movimiento(imagen_id: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")
        movimiento, prompt_imagen = img.prompt_movimiento.strip(), img.prompt or img.idea
    if not movimiento:
        raise ValueError("Escribe primero qué quieres que se mueva")

    sistema = (PROMPTS_DIR / "animada_movimiento.md").read_text()
    r = llm.chat(sistema, f"IMAGE: {prompt_imagen}\n\nMOTION: {movimiento}",
                 AnimadaMovimientoLLM)

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.guardar_movimiento(s, img, r.prompt, acotar_duracion(r.duracion_s))
        s.commit()
    return f"Movimiento pulido ({r.duracion_s} s recomendados)"


def animar(imagen_id: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")
        prompt = img.prompt_movimiento.strip()
        duracion, indice = acotar_duracion(img.duracion_s), img.seed_elegido
        width, height = img.width, img.height
    if not prompt:
        raise ValueError("Falta el prompt de movimiento")
    imagen = _imagen_aprobada(imagen_id, indice)

    frames = cuadros_para(duracion)
    w, h = tamano_generacion(width, height)
    k = ANIMADA_FPS_FINAL // ANIMADA_FPS_ORIGEN
    # RIFE mete k-1 cuadros entre cada par: (frames-1)·k+1 y el último sigue
    # siendo copia del primero. Se tira ese último y el bucle cierra limpio.
    finales = (frames - 1) * k
    seed = random.randint(0, 2**31 - 1)
    destino = ruta_video(imagen_id)

    parada.comprobar("antes de animar")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            crudo, suave = Path(tmp) / "crudo.mp4", Path(tmp) / "suave.mp4"
            progreso.lote(0, 2, "paso")
            comfy.generar_video_loop(imagen, prompt, seed, frames, ANIMADA_FPS_ORIGEN,
                                     w, h, crudo)
            # LTX ya no hace falta: RIFE y ffmpeg no lo necesitan, y lo que venga
            # después en la cola tampoco quiere encontrárselo dentro.
            comfy.liberar_memoria()
            parada.comprobar("tras animar, antes de interpolar")
            progreso.lote(1, 2, "paso")
            rife.interpolar(crudo, suave, ANIMADA_FPS_ORIGEN, ANIMADA_FPS_FINAL,
                            frames=finales + 1)
            with sin_restos(destino):
                cerrar_bucle(suave, destino, finales, ANIMADA_FUNDIDO, w, h)
    finally:
        comfy.liberar_memoria()

    # Las versiones escaladas eran del vídeo anterior.
    for escala in LADO_ESCALA:
        ruta_video(imagen_id, escala).unlink(missing_ok=True)
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.guardar_video(s, img, seed)
        s.commit()
    return (f"Bucle de {finales / ANIMADA_FPS_FINAL:.1f} s a {w}×{h}, "
            f"{frames} cuadros a {ANIMADA_FPS_ORIGEN} fps → {ANIMADA_FPS_FINAL} fps")


def escalar(imagen_id: int, escala: str) -> str:
    if escala not in LADO_ESCALA:
        raise ValueError(f"Escala desconocida: {escala}")
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")
        width, height = img.width, img.height
    origen = ruta_video(imagen_id)
    if not origen.exists():
        raise ValueError("Todavía no hay vídeo que escalar: anímalo primero")
    w, h = tamano_escala(width, height, escala)
    destino = ruta_video(imagen_id, escala)

    def paso(i: int, n: int) -> None:
        parada.comprobar(f"quedaban {n - i} cuadros por escalar")
        progreso.lote(i, n, "cuadro")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            din, dout = Path(tmp) / "in", Path(tmp) / "out"
            din.mkdir()
            procesos.ejecutar(
                ["ffmpeg", "-loglevel", "error", "-y", "-i", str(origen),
                 str(din / "%06d.png")],
                timeout=procesos.CLIP_S, que="ffmpeg (extraer cuadros)", check=True,
            )
            escalador.escalar_cuadros(din, dout, paso)
            with sin_restos(destino):
                procesos.ejecutar(
                    ["ffmpeg", "-loglevel", "error", "-y",
                     "-framerate", str(ANIMADA_FPS_FINAL), "-i", str(dout / "%06d.png"),
                     "-vf", f"scale={w}:{h}:flags=lanczos",
                     "-c:v", "libx264", "-preset", "slow", "-crf", str(ANIMADA_CRF),
                     "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
                     str(destino)],
                    timeout=procesos.MONTAJE_S, que="ffmpeg (bucle escalado)", check=True,
                )
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.guardar_escala(s, img, escala)
        s.commit()
    return f"Bucle escalado a {escala.upper()} ({w}×{h})"
