"""El lienzo del modo motion: medidas, paleta, curvas y la proyección.

Lo que hay aquí lo comparten las dos capas que dibujan —la composición de la
escena (`_motion_escena`) y los bloques de anotación (`_motion_bloques`)— y
está suelto porque si no, una tiene que importar a la otra para saber de qué
tamaño es un fotograma.

Dos cosas que mandan en todo el modo:

**Nada se coloca en la pantalla: se coloca en el mundo.** La pantalla es donde
ese sitio del mundo cae en este fotograma (`Mundo.proyectar`). Por eso una
etiqueta pegada a una pieza la sigue mientras la cámara entra, y por eso el
dibujo y la anotación **tienen que hacer la misma cuenta**: si una proyecta y
la otra estima, la etiqueta se despega de lo que señala.

**Todo se pinta al doble y se reduce** (lo hace `motion.py`), así que las
medidas de los módulos de dibujo son de pantalla y se multiplican por `s`.
"""
import math
from functools import lru_cache

ANCHO_LIENZO, ALTO_LIENZO = 1080, 1920

# La paleta de la marca. El fondo es el mismo del estudio, y el acento y la
# lima son los dos únicos colores que llaman la atención: todo lo demás es
# tinta, panel y canto.
FONDO = (13, 15, 20)           # #0d0f14
INK = (246, 241, 231)
ACENTO = (109, 94, 252)        # #6d5efc
LIMA = (195, 240, 74)
PANEL = (19, 22, 29)           # el relleno de una pieza, un pelo sobre el fondo
FILO = (54, 57, 66)            # el canto de luz: una caja oscura sin filo no existe
APOYO = (150, 147, 139)
TENUE = (34, 38, 47)           # la rejilla del fondo y los vínculos dormidos
ALERTA = (255, 77, 46)         # el fallo
CALOR = (255, 138, 42)         # lo que se sobrecalienta


def mezcla(fondo: tuple, tinta: tuple, alfa: float) -> tuple:
    """Tinta translúcida sobre un fondo conocido, resuelta de antemano.

    Dibujar con alfa de verdad obliga a una capa RGBA y a componerla. Para lo
    que siempre cae sobre un fondo que ya se sabe —la rejilla, las rayas de un
    carril, el halo de una pieza caliente— sale mucho más barato calcular el
    color una vez.
    """
    return tuple(round(f + (t - f) * alfa) for f, t in zip(fondo, tinta))


def sembrar(a: int):
    """mulberry32: barato, sin estado global y siempre la misma serie."""
    def r() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = (a ^ (a >> 15)) * (1 | a) & 0xFFFFFFFF
        t = ((t + ((t ^ (t >> 7)) * (61 | t) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return r


# ── Curvas ────────────────────────────────────────────────────────────────
# Las de siempre del motion, en diez líneas y sin librería.
def tope(p: float) -> float:
    return 0.0 if p < 0 else (1.0 if p > 1 else p)


def salida(p: float, n: int = 4) -> float:
    return 1 - (1 - tope(p)) ** n


def entrada_salida(p: float) -> float:
    p = tope(p)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def rebote(p: float, s: float = 1.8) -> float:
    p = tope(p) - 1
    return p * p * ((s + 1) * p + s) + 1


def tramo(t: float, desde: float, dura: float) -> float:
    """Cuánto ha avanzado una animación que empieza en `desde` y dura `dura`."""
    return tope((t - desde) / dura) if dura > 0 else 1.0


def respira(t: float, periodo: float) -> float:
    """Un 0→1→0 suave que se repite. Lo que late, lo que calienta."""
    return (1 - math.cos(2 * math.pi * (t % periodo) / periodo)) / 2


# ── El mundo y la cámara ──────────────────────────────────────────────────
class Mundo:
    """Lo que sabe colocar un sitio del mundo en la pantalla.

    Las subclases ponen `ancho` y `alto` (y su `encuadre`, que es el zoom al
    que cabe entero); de aquí sacan la cámara y la proyección.
    """

    ancho: float = ANCHO_LIENZO
    alto: float = ALTO_LIENZO

    def _centro(self, cam: dict) -> tuple[float, float]:
        """La cámara nunca se sale del mundo: con zoom de sobra va donde
        quiere, y cuando no, se queda centrada."""
        mx, my = ANCHO_LIENZO / 2 / cam["z"], ALTO_LIENZO / 2 / cam["z"]
        return (self.ancho / 2 if mx * 2 >= self.ancho
                else min(max(cam["x"], mx), self.ancho - mx),
                self.alto / 2 if my * 2 >= self.alto
                else min(max(cam["y"], my), self.alto - my))

    def proyectar(self, cam: dict, wx: float, wy: float,
                  s: int = 1) -> tuple[float, float]:
        """Mundo → pantalla."""
        px, py = self._centro(cam)
        r = math.radians(cam.get("rot", 0.0))
        co, si = math.cos(r), math.sin(r)
        dx, dy = (wx - px) * cam["z"] * s, (wy - py) * cam["z"] * s
        return (ANCHO_LIENZO * s / 2 + dx * co - dy * si,
                ALTO_LIENZO * s / 2 + dx * si + dy * co)


@lru_cache(maxsize=2)
def vineta(ancho: int, alto: int):
    """Máscara para oscurecer los bordes. Se calcula una vez y se pega en cada
    fotograma: hacerla por píxel en cada cuadro costaría más que la escena."""
    from PIL import Image

    peq = Image.new("L", (ancho // 10, alto // 10))
    px = peq.load()
    w, h = peq.size
    for y in range(h):
        for x in range(w):
            dx = (x - w / 2) / (w * 0.62)
            dy = (y - h * 0.44) / (h * 0.39)
            r = math.hypot(dx, dy)
            px[x, y] = round(255 * min(1.0, max(0.0, (r - 0.55) / 0.75)) * 0.72)
    return peq.resize((ancho, alto), Image.BICUBIC)
