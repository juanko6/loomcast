"""Armado en modo MOVIMIENTO: concat de clips Ken Burns + subtítulos + voz.

Concatena los clips (60fps), superpone los subtítulos rasterizados a PNG
transparentes (Pillow) con el filtro `overlay` de ffmpeg (cada uno activo en
su ventana de tiempo) y añade la narración.
"""
import subprocess

from ...config import PROYECTOS_DIR, VIDEO_COLA_FINAL_S
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from . import _subtitulos_render as subs
from ._ffmpeg import archivar_final, args_video, duracion


def _rasterizar_transparente(texto, fuente, color, borde, destino):
    from PIL import Image

    img = Image.new("RGBA", (subs.ANCHO, subs.ALTO), (0, 0, 0, 0))
    subs.dibujar_subtitulo(img, texto, fuente, color, borde)
    img.save(destino)


def armar_video(proyecto_id: int) -> str:
    import soundfile as sf

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        ordenes = [e.orden for e in escenas_repo.por_proyecto(s, proyecto_id)]
        slug, plantilla = p.slug, p.plantilla

    base = PROYECTOS_DIR / slug
    if not ordenes:
        raise ValueError("No hay escenas")
    faltantes = [o for o in ordenes if not (base / "clips" / f"{o:02d}.mp4").exists()]
    if faltantes:
        raise ValueError(f"Faltan clips de las escenas {faltantes}")
    if not (base / "voz.wav").exists() or not (base / "subtitulos.srt").exists():
        raise ValueError("Faltan voz.wav o subtitulos.srt")

    (base / "clips_concat.txt").write_text(
        "\n".join(f"file 'clips/{o:02d}.mp4'" for o in ordenes) + "\n"
    )

    pl = plantillas_repo.cargar(plantilla)
    sub_cfg = pl["subtitulos"]
    fuente = subs.buscar_fuente(sub_cfg.get("fuente", "Arial Bold"))
    if fuente is None:
        raise RuntimeError("No se encontró ninguna fuente para los subtítulos")
    color, borde = sub_cfg.get("color", "#FFFFFF"), sub_cfg.get("borde", "#000000")

    bloques = subs.srt_a_bloques(base / "subtitulos.srt")
    subs_dir = base / "subs"
    subs_dir.mkdir(exist_ok=True)
    for i, b in enumerate(bloques):
        _rasterizar_transparente(b["texto"], fuente, color, borde, subs_dir / f"{i:03d}.png")

    cmd = ["ffmpeg", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", "clips_concat.txt"]
    for i in range(len(bloques)):
        cmd += ["-loop", "1", "-i", f"subs/{i:03d}.png"]
    cmd += ["-i", "voz.wav"]
    idx_audio = len(bloques) + 1

    cadena, prev = [], "[0:v]"
    for i, b in enumerate(bloques):
        etiqueta = f"[o{i}]"
        cadena.append(
            f"{prev}[{i + 1}:v]overlay=0:0"
            f":enable='between(t,{b['start']:.3f},{b['end']:.3f})'{etiqueta}"
        )
        prev = etiqueta

    # El video termina con las imágenes, no con la voz: dura lo que duren los
    # clips y, si se quedan cortos, se congela el último cuadro para dejar una
    # cola tras la última palabra en vez de cortar en seco.
    dur_audio = sf.info(base / "voz.wav").duration
    dur_clips = sum(duracion(base / "clips" / f"{o:02d}.mp4") for o in ordenes)
    objetivo = max(dur_clips, dur_audio + VIDEO_COLA_FINAL_S)
    cadena.append(f"{prev}tpad=stop_mode=clone:stop_duration={objetivo:.3f}[vout]")
    filtro = ";".join(cadena)

    cmd += ["-filter_complex", filtro,
            "-map", "[vout]", "-map", f"{idx_audio}:a",
            *args_video(), "-r", "60",
            "-c:a", "aac", "-b:a", "192k",
            # apad + -t: el audio se rellena con silencio hasta el final del
            # video, para que no quede un stream de audio más corto.
            "-af", "apad", "-t", f"{objetivo:.3f}", "final.mp4"]

    archivada = archivar_final(base)
    r = subprocess.run(cmd, cwd=base, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {r.stderr[-800:]}")

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "FINAL")
        s.commit()
    cola = objetivo - dur_audio
    guardado = f"; el anterior queda en versiones/{archivada}" if archivada else ""
    return (f"Video (movimiento): {len(ordenes)} escenas, {objetivo:.1f}s "
            f"({cola:.1f}s tras la voz) → final.mp4{guardado}")
