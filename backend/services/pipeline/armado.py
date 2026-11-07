"""Armado en modo MOVIMIENTO: concat de clips Ken Burns + subtítulos + voz.

Concatena los clips (60fps), superpone los subtítulos rasterizados a PNG
transparentes (Pillow) con el filtro `overlay` de ffmpeg (cada uno activo en
su ventana de tiempo) y añade la narración. Si el proyecto tiene la mezcla de
música activada, la cama entra por debajo de la voz con ducking (ver _mezcla).
"""

from ... import procesos
from ...config import PROYECTOS_DIR, VIDEO_COLA_FINAL_S
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from . import _marca, _mezcla
from . import _subtitulos_render as subs
from ._ffmpeg import archivar_final, args_video, duracion, sin_restos


def _rasterizar_transparente(texto, fuente, color, borde, destino,
                             posicion="abajo", tam=subs.TAM_FUENTE):
    from PIL import Image

    img = Image.new("RGBA", (subs.ANCHO, subs.ALTO), (0, 0, 0, 0))
    subs.dibujar_subtitulo(img, texto, fuente, color, borde, posicion, tam)
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
    # Se resuelve antes de rasterizar subtítulos: si la mezcla está activada y
    # la pista no está, mejor fallar ya que tras varios minutos de render.
    musica = _mezcla.pista_a_mezclar(proyecto_id)
    # ffmpeg sale con código 0 aunque el concat no consiga abrir un clip (corrupto
    # o a medio escribir): lo salta y entrega un video al que le falta esa escena.
    # Se comprueba antes que cada clip tenga duración legible.
    ilegibles = [o for o in ordenes if not duracion(base / "clips" / f"{o:02d}.mp4")]
    if ilegibles:
        raise ValueError(
            f"Los clips de las escenas {ilegibles} están corruptos o incompletos; "
            "regéneralos antes de armar el video"
        )

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
    # Dónde y de qué tamaño los quiere la plantilla. En motion van arriba y
    # pequeños, porque abajo vive el titular (ver `_motion_bloques`).
    posicion = sub_cfg.get("posicion", "abajo")
    tam = int(sub_cfg.get("tam", subs.TAM_FUENTE))
    for i, b in enumerate(bloques):
        _rasterizar_transparente(b["texto"], fuente, color, borde,
                                 subs_dir / f"{i:03d}.png", posicion, tam)

    # Marca de episodio: vacía si el proyecto no es de una serie, y entonces no
    # se añade ni la entrada ni el overlay (el montaje de un vídeo suelto no
    # cambia en nada).
    marca = _marca.de_proyecto(proyecto_id)
    if marca:
        _marca.rasterizar(marca, fuente, color, borde, base / "marca.png")

    cmd = ["ffmpeg", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", "clips_concat.txt"]
    for i in range(len(bloques)):
        cmd += ["-loop", "1", "-i", f"subs/{i:03d}.png"]
    cmd += ["-i", "voz.wav"]
    idx_audio = len(bloques) + 1
    idx_musica = idx_audio + 1
    if musica:
        cmd += ["-i", str(musica)]
    # La marca va de última entrada para no mover los índices del audio, que es
    # lo que la cadena de mezcla tiene que saber.
    idx_marca = (idx_musica if musica else idx_audio) + 1
    if marca:
        cmd += ["-loop", "1", "-i", "marca.png"]

    cadena, prev = [], "[0:v]"
    if marca:
        # Sin `enable`: la marca está todo el vídeo. Va antes de los subtítulos
        # para que, si alguno subiera hasta ahí, se dibuje encima de ella.
        cadena.append(f"{prev}[{idx_marca}:v]overlay=0:0[marca]")
        prev = "[marca]"
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

    # Sin música: la voz se mapea directa y `-af apad` la rellena con silencio
    # hasta el final del video. Con música, toda la cadena de audio vive en el
    # filter_complex (ffmpeg no admite `-af` sobre un stream que sale de ahí) y
    # el apad va dentro.
    if musica:
        cadena.append(_mezcla.cadena(idx_audio, idx_musica, objetivo, duracion(musica)))
        audio, af = "[aout]", []
    else:
        audio, af = f"{idx_audio}:a", ["-af", "apad"]
    filtro = ";".join(cadena)

    cmd += ["-filter_complex", filtro,
            "-map", "[vout]", "-map", audio,
            *args_video(), "-r", "60",
            "-c:a", "aac", "-b:a", "192k",
            *af, "-t", f"{objetivo:.3f}", "final.mp4"]

    archivada = archivar_final(base)
    # El montaje escribe sobre final.mp4 y el anterior ya está archivado: si se
    # corta a medias, lo que queda ahí es un vídeo truncado que la UI ofrecería
    # como el final. Se borra y el proyecto vuelve a estar "sin vídeo", con sus
    # versiones anteriores intactas.
    with sin_restos(base / "final.mp4"):
        r = procesos.ejecutar(cmd, timeout=procesos.MONTAJE_S, que="ffmpeg (montaje)",
                              cwd=base, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falló: {r.stderr[-800:]}")

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "FINAL")
        s.commit()
    cola = objetivo - dur_audio
    guardado = f"; el anterior queda en versiones/{archivada}" if archivada else ""
    con_musica = f"; con música ({musica.parent.name})" if musica else ""
    con_marca = f"; marcado «{marca}»" if marca else ""
    return (f"Video (movimiento): {len(ordenes)} escenas, {objetivo:.1f}s "
            f"({cola:.1f}s tras la voz) → final.mp4{con_musica}{con_marca}{guardado}")
