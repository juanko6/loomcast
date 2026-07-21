"""Utilidades de subtítulos compartidas por los armados (estático y movimiento).

El ffmpeg de brew no trae libass, así que los subtítulos se rasterizan con
Pillow: aquí viven la búsqueda de fuente, el parseo del SRT y el dibujo del
texto (centrado abajo, con borde) sobre cualquier imagen.
"""
import re
from pathlib import Path

ANCHO, ALTO = 1080, 1920
TAM_FUENTE = 88
MARGEN_INFERIOR = 420
ANCHO_MAX_TEXTO = 980

DIRS_FUENTES = [
    Path.home() / "Library/Fonts",
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
]


def srt_a_bloques(srt: Path) -> list[dict]:
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


def buscar_fuente(nombre: str) -> Path | None:
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


def dibujar_subtitulo(img, texto: str, fuente_path: Path, color: str, borde: str):
    """Dibuja el texto centrado en la franja inferior de `img` (RGB o RGBA)."""
    from PIL import ImageDraw, ImageFont

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
    return img
