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
MARGEN_SUPERIOR = 120
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


def dibujar_subtitulo(img, texto: str, fuente_path: Path, color: str, borde: str,
                      posicion: str = "abajo", tam: int = TAM_FUENTE):
    """Dibuja el texto centrado en una franja de `img` (RGB o RGBA).

    Arriba y pequeño es para el modo motion, donde el tercio de abajo lo ocupa
    la capa de titulares: dos textos grandes en el mismo sitio no se leen ni
    por separado. El subtítulo pasa entonces a ser lo que es en ese lenguaje
    —la transcripción literal, de apoyo— y el titular se queda con el peso.
    """
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)
    grosor = max(2, round(tam / 15))
    minimo = max(24, tam // 2)
    while tam > minimo:
        font = ImageFont.truetype(str(fuente_path), tam)
        caja = draw.textbbox((0, 0), texto, font=font, stroke_width=grosor)
        if caja[2] - caja[0] <= ANCHO_MAX_TEXTO:
            break
        tam -= 6
    else:
        font = ImageFont.truetype(str(fuente_path), tam)
        caja = draw.textbbox((0, 0), texto, font=font, stroke_width=grosor)
    x = (ANCHO - (caja[2] - caja[0])) // 2 - caja[0]
    y = (MARGEN_SUPERIOR - caja[1] if posicion == "arriba"
         else ALTO - MARGEN_INFERIOR - (caja[3] - caja[1]))
    draw.text((x, y), texto, font=font, fill=color, stroke_width=grosor,
              stroke_fill=borde)
    return img
