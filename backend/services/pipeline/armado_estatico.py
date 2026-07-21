"""Armado en modo ESTÁTICO: imágenes fijas + subtítulos quemados + voz.

Rápido (sin ESRGAN ni clips): usa las imágenes de escena directamente. Corta
la línea de tiempo en cada frontera de escena o de subtítulo, estampa el texto
sobre la imagen activa (1080x1920) y concatena los stills con sus duraciones.
Ideal para iterar guion/voz/prompts sin esperar el render con movimiento.
"""
import subprocess

from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from . import _subtitulos_render as subs
from ._ffmpeg import args_video


def armar_estatico(proyecto_id: int) -> str:
    import soundfile as sf
    from PIL import Image

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            {"orden": e.orden, "t_inicio": e.t_inicio, "t_fin": e.t_fin}
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]
        slug, plantilla = p.slug, p.plantilla

    base = PROYECTOS_DIR / slug
    if not escenas:
        raise ValueError("No hay escenas")
    faltantes = [e["orden"] for e in escenas
                 if not (base / "imagenes" / f"{e['orden']:02d}.png").exists()]
    if faltantes:
        raise ValueError(f"Faltan imágenes de las escenas {faltantes}")
    if not (base / "voz.wav").exists() or not (base / "subtitulos.srt").exists():
        raise ValueError("Faltan voz.wav o subtitulos.srt")

    pl = plantillas_repo.cargar(plantilla)
    sub_cfg = pl["subtitulos"]
    fuente = subs.buscar_fuente(sub_cfg.get("fuente", "Arial Bold"))
    if fuente is None:
        raise RuntimeError("No se encontró ninguna fuente para los subtítulos")
    color, borde = sub_cfg.get("color", "#FFFFFF"), sub_cfg.get("borde", "#000000")

    bloques = subs.srt_a_bloques(base / "subtitulos.srt")
    dur_audio = sf.info(base / "voz.wav").duration

    # Cortes de la línea de tiempo: fronteras de escena y de subtítulo
    cortes = {0.0, dur_audio}
    for e in escenas:
        cortes.update((e["t_inicio"], e["t_fin"]))
    for b in bloques:
        cortes.update((b["start"], b["end"]))
    cortes = sorted(t for t in cortes if 0 <= t <= dur_audio)

    def escena_en(t):
        return next((e for e in escenas if e["t_inicio"] <= t < e["t_fin"]), escenas[-1])

    def bloque_en(t):
        return next((b["texto"] for b in bloques if b["start"] <= t < b["end"]), None)

    armado_dir = base / "armado"
    armado_dir.mkdir(exist_ok=True)
    fondos: dict[int, Image.Image] = {}

    def fondo(orden):
        if orden not in fondos:
            img = Image.open(base / "imagenes" / f"{orden:02d}.png").convert("RGB")
            escala = max(subs.ANCHO / img.width, subs.ALTO / img.height)
            img = img.resize((round(img.width * escala), round(img.height * escala)))
            x = (img.width - subs.ANCHO) // 2
            y = (img.height - subs.ALTO) // 2
            fondos[orden] = img.crop((x, y, x + subs.ANCHO, y + subs.ALTO))
        return fondos[orden]

    lineas, stills = [], {}
    clave = None
    for i in range(len(cortes) - 1):
        t0, t1 = cortes[i], cortes[i + 1]
        if t1 - t0 < 0.01:
            continue
        e = escena_en(t0)
        texto = bloque_en(t0 + 0.005)
        clave = (e["orden"], texto)
        if clave not in stills:
            nombre = f"{len(stills):03d}.png"
            img = fondo(e["orden"]).copy()
            if texto:
                subs.dibujar_subtitulo(img, texto, fuente, color, borde)
            img.save(armado_dir / nombre)
            stills[clave] = nombre
        lineas.append(f"file 'armado/{stills[clave]}'")
        lineas.append(f"duration {t1 - t0:.3f}")
    lineas.append(f"file 'armado/{stills[clave]}'")
    (base / "estatico_concat.txt").write_text("\n".join(lineas) + "\n")

    r = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", "estatico_concat.txt",
         "-i", "voz.wav", "-vf", "fps=30",
         *args_video(),
         "-c:a", "aac", "-b:a", "192k", "-shortest", "final.mp4"],
        cwd=base, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {r.stderr[-800:]}")

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "FINAL")
        s.commit()
    return f"Video (estático): {len(escenas)} escenas, {dur_audio:.1f}s → final.mp4"
