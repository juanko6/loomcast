"""Etapa 11 — ARMADO: video final con movimiento + subtítulos + voz.

Concatena los clips Ken Burns (60fps), superpone los subtítulos y añade la
narración. El ffmpeg de brew no trae libass, así que los subtítulos se
rasterizan con Pillow a PNG transparentes (1080x1920) y se superponen con el
filtro `overlay` de ffmpeg, cada uno activo en su ventana de tiempo.
"""
import re
import subprocess
from pathlib import Path

from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo

ANCHO, ALTO = 1080, 1920
TAM_FUENTE = 88
MARGEN_INFERIOR = 420
ANCHO_MAX_TEXTO = 980

DIRS_FUENTES = [
    Path.home() / "Library/Fonts",
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
]


def _srt_a_bloques(srt: Path) -> list[dict]:
    def a_seg(t: str) -> float:
        h, m, resto = t.split(":")
        s, ms = resto.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    bloques = re.findall(
        r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?:\n\n|\n?$)",
        srt.read_text(),
        re.DOTALL,
    )
    return [
        {"start": a_seg(i), "end": a_seg(f), "texto": " ".join(t.split())}
        for i, f, t in bloques
    ]


def _buscar_fuente(nombre: str) -> Path | None:
    objetivo = re.sub(r"[^a-z0-9]", "", nombre.lower())
    candidatos = []
    for d in DIRS_FUENTES:
        if d.exists():
            candidatos += [p for p in d.iterdir() if p.suffix in (".ttf", ".otf")]
    for p in candidatos:
        if re.sub(r"[^a-z0-9]", "", p.stem.lower()) == objetivo:
            return p
    for p in candidatos:
        if objetivo in re.sub(r"[^a-z0-9]", "", p.stem.lower()):
            return p
    for respaldo in ("Arial Bold.ttf", "Helvetica.ttc"):
        p = Path("/System/Library/Fonts/Supplemental") / respaldo
        if p.exists():
            return p
    return None


def _rasterizar_subtitulo(texto: str, fuente_path: Path, color: str, borde: str, destino: Path):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tam = TAM_FUENTE
    while tam > 40:
        font = ImageFont.truetype(str(fuente_path), tam)
        caja = draw.textbbox((0, 0), texto, font=font, stroke_width=6)
        if caja[2] - caja[0] <= ANCHO_MAX_TEXTO:
            break
        tam -= 6
    x = (ANCHO - (caja[2] - caja[0])) // 2 - caja[0]
    y = ALTO - MARGEN_INFERIOR - (caja[3] - caja[1])
    draw.text((x, y), texto, font=font, fill=color, stroke_width=6, stroke_fill=borde)
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

    # 1. Lista de clips para el demuxer concat
    lista = "\n".join(f"file 'clips/{o:02d}.mp4'" for o in ordenes)
    (base / "clips_concat.txt").write_text(lista + "\n")

    # 2. Rasterizar cada bloque de subtítulos a PNG transparente
    pl = plantillas_repo.cargar(plantilla)
    sub_cfg = pl["subtitulos"]
    fuente = _buscar_fuente(sub_cfg.get("fuente", "Arial Bold"))
    if fuente is None:
        raise RuntimeError("No se encontró ninguna fuente para los subtítulos")
    color, borde = sub_cfg.get("color", "#FFFFFF"), sub_cfg.get("borde", "#000000")

    bloques = _srt_a_bloques(base / "subtitulos.srt")
    subs_dir = base / "subs"
    subs_dir.mkdir(exist_ok=True)
    for i, b in enumerate(bloques):
        _rasterizar_subtitulo(b["texto"], fuente, color, borde, subs_dir / f"{i:03d}.png")

    # 3. Montaje en una sola pasada: clips (concat) + overlays de subtítulos + voz
    cmd = ["ffmpeg", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", "clips_concat.txt"]
    for i in range(len(bloques)):
        cmd += ["-loop", "1", "-i", f"subs/{i:03d}.png"]
    cmd += ["-i", "voz.wav"]
    idx_audio = len(bloques) + 1

    cadena, prev = [], "[0:v]"
    for i, b in enumerate(bloques):
        etiqueta = "[vout]" if i == len(bloques) - 1 else f"[o{i}]"
        cadena.append(
            f"{prev}[{i + 1}:v]overlay=0:0:enable='between(t,{b['start']:.3f},{b['end']:.3f})'{etiqueta}"
        )
        prev = etiqueta
    filtro = ("[0:v]null[vout]" if not bloques else ";".join(cadena))

    cmd += ["-filter_complex", filtro,
            "-map", "[vout]", "-map", f"{idx_audio}:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", "60",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "final.mp4"]

    r = subprocess.run(cmd, cwd=base, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {r.stderr[-800:]}")

    dur = sf.info(base / "voz.wav").duration
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "FINAL")
        s.commit()
    return f"Video final con movimiento: {len(ordenes)} escenas, {dur:.1f}s → final.mp4"
