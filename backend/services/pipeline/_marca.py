"""Marca de episodio: el «EP 3» de una serie, estampado en el vídeo.

Un episodio suelto en un feed no se lee como episodio: la marca es lo que dice
al espectador que hay un antes y un después, y es lo que hace que busque el
anterior. Va quemada en el vídeo porque el título de la publicación se corta y
no viaja cuando alguien reenvía el archivo.

Se dibuja con Pillow, igual que los subtítulos y por el mismo motivo (el ffmpeg
de brew no trae libass), y toma la fuente y los colores de los subtítulos de la
plantilla: es el vídeo el que tiene un look, no la marca.

**Un proyecto que no es episodio no tiene marca**: `de_proyecto` devuelve cadena
vacía y los dos armados se saltan el overlay entero, así que su montaje es el de
siempre.
"""
from ...db import get_session
from ...repositories import proyectos as proyectos_repo
from ...repositories import series as series_repo
from . import _subtitulos_render as subs

# Caja de la marca: arriba a la izquierda, por debajo de la zona que las apps
# tapan con su interfaz (en 9:16 el nombre del canal y el botón de seguir).
MARGEN_X = 56
MARGEN_Y = 150
TAM_FUENTE = 52
ANCHO_MAX = 760


def de_proyecto(proyecto_id: int) -> str:
    """El texto de la marca, o "" si el proyecto no es un episodio."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None or p.serie_id is None or not p.episodio:
            return ""
        serie = series_repo.obtener(s, p.serie_id)
        if serie is None:
            return ""
        return texto_marca(serie.nombre, p.episodio)


def texto_marca(nombre_serie: str, episodio: int) -> str:
    """«LA CASA DE ALICIA · EP 3».

    El nombre de la serie va delante porque el número solo no dice de qué es, y
    en mayúsculas para que se lea de un vistazo a tamaño de móvil. Un nombre
    larguísimo se recorta aquí y no al dibujar: así la marca nunca se come media
    pantalla ni se encoge hasta ser ilegible.
    """
    nombre = " ".join((nombre_serie or "").split()).upper()
    if len(nombre) > 28:
        nombre = nombre[:27].rstrip() + "…"
    return f"{nombre} · EP {episodio}" if nombre else f"EP {episodio}"


def dibujar(img, texto: str, fuente_path, color: str, borde: str):
    """Estampa la marca arriba a la izquierda de `img` (RGB o RGBA)."""
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)
    tam = TAM_FUENTE
    while tam > 28:
        font = ImageFont.truetype(str(fuente_path), tam)
        caja = draw.textbbox((0, 0), texto, font=font, stroke_width=4)
        if caja[2] - caja[0] <= ANCHO_MAX:
            break
        tam -= 4
    draw.text((MARGEN_X, MARGEN_Y), texto, font=font, fill=color,
              stroke_width=4, stroke_fill=borde)
    return img


def rasterizar(texto: str, fuente_path, color: str, borde: str, destino) -> None:
    """La marca sola sobre transparente, para el `overlay` de ffmpeg.

    El armado con movimiento compone sobre un vídeo, no sobre imágenes: como con
    los subtítulos, se rasteriza un PNG del tamaño del cuadro y se superpone,
    aquí sin ventana de tiempo porque la marca está todo el vídeo.
    """
    from PIL import Image

    img = Image.new("RGBA", (subs.ANCHO, subs.ALTO), (0, 0, 0, 0))
    dibujar(img, texto, fuente_path, color, borde)
    img.save(destino)
