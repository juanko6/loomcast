"""Etapa 9 (motion) — CLIPS: una composición dibujada por escena, a 60fps.

El modo motion no genera imágenes ni las anima: **dibuja** cada fotograma. Por
cada escena monta su composición (`_motion_escena`), le pasa la cámara que le
toca y le pone encima su bloque de anotación (`_motion_bloques`), y le va dando
los cuadros crudos a ffmpeg según salen, sin pasar por disco.

Tres decisiones que se notan en pantalla:

**Cada escena trae su dibujo.** No hay decorado compartido ni semilla del
proyecto: la composición entera está en la ficha de la escena, ya resuelta.
Una escena que continuaba a la anterior heredó sus piezas cuando se generó
(ver `_motion_ficha.revisar_dibujo`), así que aquí no hay cadena que recorrer y
rehacer un clip suelto no depende de los demás.

**El reloj de cada clip empieza en cero.** Lo que se anima es de la escena —un
dato que cruza, una pila que se llena—, y empieza cuando empieza la escena.

**Las escenas no duran todas lo mismo.** La duración sale del corte por frases
(ver `_motion_frases`), así que un clip puede durar dos segundos y el siguiente
nueve.

Sale a 1080x1920 y 60fps como los demás modos, porque el armado los concatena
todos juntos.
"""
import json
import time
from pathlib import Path

from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ... import parada, procesos
from ...repositories import escenas as escenas_repo
from ...repositories import proyectos as proyectos_repo
from .. import progreso
from . import _motion_bloques as bloques
from ._ffmpeg import args_video, sin_restos
from ._motion_escena import Escenario, camara
from ._motion_lienzo import ALTO_LIENZO, ANCHO_LIENZO, FONDO, vineta
from .clips import pendientes_de_modo

FPS = 60
# Se dibuja al doble y se reduce: esa media de cada 2x2 es el antialias, y es
# lo que hace que los bordes no hiervan de un cuadro al otro.
SUPER = 2


def _titulares(guardados, e) -> list[dict]:
    """Los titulares de la escena, con lo que diga la UI por encima.

    Lo que se lee en pantalla viaja en `escena.prompt` —un titular por línea,
    donde las demás plantillas llevan el prompt visual—, porque es el campo que
    la pantalla de escenas enseña y deja corregir, y corregirlo tiene que
    cambiar el vídeo. Los tiempos no están ahí: son del audio y se quedan en la
    ficha, así que reescribir un titular cambia lo que se lee sin tocar cuándo
    se lee.
    """
    lineas = [l.strip() for l in (e.prompt or "").split("\n") if l.strip()]
    salida = [
        {"texto": lineas[k] if k < len(lineas) else (tt.get("texto") or ""),
         "enfasis": tt.get("enfasis") or [],
         "t0": float(tt.get("t0") or 0.0),
         "t1": float(tt.get("t1") or 0.0)}
        for k, tt in enumerate(guardados or [])
    ]
    if salida or not lineas:
        return salida
    # Una ficha de antes de que existiera esta capa, o rota: que se lea algo,
    # repartido a ojo por la escena. Feo, pero es un clip.
    dur = max(0.1, e.t_fin - e.t_inicio)
    return [{"texto": l, "enfasis": [], "t0": k * dur / len(lineas),
             "t1": (k + 1) * dur / len(lineas)}
            for k, l in enumerate(lineas)]


def _ficha(e) -> dict:
    """La composición de la escena, con sus valores por defecto.

    Una ficha rota no puede tumbar el render: sin dibujo queda el titular sobre
    negro, que es un clip feo pero es un clip.
    """
    try:
        f = json.loads(e.ficha) if e.ficha else {}
    except json.JSONDecodeError:
        f = {}
    f.setdefault("bloque", "NADA")
    f.setdefault("banda", "centro")
    f["titulares"] = _titulares(f.get("titulares"), e)
    if not f["titulares"]:
        f["titulares"] = [{"texto": e.texto.split(".")[0][:70], "enfasis": [],
                           "t0": 0.0, "t1": max(0.1, e.t_fin - e.t_inicio)}]
    f.setdefault("texto", "")
    f.setdefault("chapa", "")
    f.setdefault("filas", [])
    f.setdefault("apoyo", "")
    f.setdefault("enfasis", [])
    f.setdefault("camara", "general")
    f.setdefault("fondo", "negro")
    f.setdefault("piezas", [])
    f.setdefault("vinculos", [])
    f.setdefault("animacion", {"tipo": "nada"})
    f.setdefault("foco", "")
    return f


def clip_motion(ficha: dict, orden: int, dur: float, salida: Path) -> None:
    """Dibuja la escena entera y se la va dando a ffmpeg cuadro a cuadro."""
    from PIL import Image, ImageDraw

    frames = max(1, round(dur * FPS))
    esc = Escenario(ficha, dur)
    # La píldora se engancha al canto de la pieza y el círculo al centro: una
    # píldora clavada en medio taparía el nombre de lo que está señalando.
    ficha = {**ficha, "ancla": esc.ancla(esc.foco, borde=ficha["bloque"] == "PILDORA")}
    sombra = vineta(ANCHO_LIENZO, ALTO_LIENZO)

    def alimentar(entrada):
        for n in range(frames):
            if n % 60 == 0:
                # Entre segundo y segundo: parar aquí deja el clip a medias,
                # pero `sin_restos` lo borra y la escena vuelve a pendiente.
                parada.comprobar(f"dibujando la escena {orden}")
            t = n / FPS
            cam = camara(ficha["camara"], esc, n / max(1, frames - 1),
                         ficha["banda"])
            im = Image.new("RGB", (ANCHO_LIENZO * SUPER, ALTO_LIENZO * SUPER), FONDO)
            esc.pintar(ImageDraw.Draw(im), cam, t, SUPER)
            im = im.reduce(SUPER)
            # La viñeta va entre el dibujo y la anotación: oscurece el decorado,
            # no el texto.
            im.paste(FONDO, (0, 0), sombra)
            bloques.dibujar(im, ficha, esc, cam, t, 1)
            entrada.write(im.tobytes())

    procesos.ejecutar_alimentado(
        ["ffmpeg", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{ANCHO_LIENZO}x{ALTO_LIENZO}", "-r", str(FPS), "-i", "-",
         "-frames:v", str(frames), *args_video(), str(salida)],
        timeout=procesos.CLIP_S, que=f"ffmpeg motion (escena {orden})",
        alimentar=alimentar,
    )


def generar_clips_motion(proyecto_id: int, forzar: bool = False) -> str:
    """Un clip dibujado por escena. Salta las que ya tengan uno de este modo,
    así que reanudar una tanda no rehace lo que ya estaba."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            {"orden": e.orden, "dur": e.t_fin - e.t_inicio,
             "clip_modo": e.clip_modo, "ficha": _ficha(e)}
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]
        slug = p.slug

    if not escenas:
        raise ValueError("El proyecto no tiene escenas")

    clips_dir = PROYECTOS_DIR / slug / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    pendientes = pendientes_de_modo(clips_dir, escenas, "motion", forzar)
    if not pendientes:
        return f"Los {len(escenas)} clips de motion ya estaban hechos"

    for i, e in enumerate(pendientes):
        parada.comprobar(f"quedaban {len(pendientes) - i} clips")
        progreso.lote(i, len(pendientes), "clip")
        t0 = time.time()
        destino = clips_dir / f"{e['orden']:02d}.mp4"
        with sin_restos(destino):
            clip_motion(e["ficha"], e["orden"], e["dur"], destino)
        with get_session() as s:
            escenas_repo.anotar_clip(s, proyecto_id, e["orden"], "motion",
                                     time.time() - t0)
            s.commit()

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "CLIPS")
        s.commit()
    saltadas = len(escenas) - len(pendientes)
    return (f"{len(pendientes)} clips dibujados"
            + (f" ({saltadas} ya estaban)" if saltadas else ""))
