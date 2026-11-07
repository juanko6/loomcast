"""Lo que se escribe encima del esquema: titulares, chapa y bloques.

La capa de texto es lo que convierte un dibujo bonito en un vídeo que explica
algo. Son tres capas y no una, y cada una tiene su sitio fijo:

**El titular, abajo, uno por frase.** Es la capa que manda. Se releva con la
voz —cada frase de la narración trae el suyo, con sus tiempos de
`palabras.json`— y por eso la pantalla nunca se queda quieta. Antes había una
sola tarjeta por escena, y una escena puede durar nueve segundos: el vídeo se
congelaba justo donde se estaba explicando lo importante.

**La chapa, arriba, toda la escena.** Dice dónde estamos en el recorrido
(`2 DE 5`, `INCIDENTE REAL`). No se mueve ni se releva: es el marco.

**El bloque, en medio, uno por escena y a veces ninguno.** Lo que señala algo
concreto de este plano: el óvalo sobre una pieza, el numeral enorme, la lista
que se enumera. `NADA` es una elección legítima y la más común: escenario,
titular y chapa ya cuentan la toma.

Dos cosas que no son evidentes y aquí mandan:

**El anclaje.** Una anotación no se coloca en la pantalla: se engancha a un
sitio del mundo, y la pantalla es donde ese sitio cae en cada fotograma (ver
`Mundo.proyectar`). Por eso el óvalo sigue pegado a su pieza mientras la cámara
entra. Si el anclaje se sale del encuadre, la anotación no se difumina: no se
dibuja.

**La banda.** El bloque declara en qué tercio va, y dos escenas seguidas no
pueden usar el mismo. Sin eso el vídeo parece atascado. El titular, en cambio,
no elige: vive siempre en el mismo sitio, que es donde el ojo lo busca.

Todo se dibuja al doble de tamaño (lo reduce `motion.py`), así que las medidas
de aquí son de pantalla y se multiplican por `s`.
"""
import math
import re
from functools import lru_cache
from pathlib import Path

from ._motion_lienzo import (ACENTO, ALTO_LIENZO, ANCHO_LIENZO, APOYO, FILO,
                             INK, LIMA, PANEL, entrada_salida, mezcla, rebote,
                             salida, tramo)
from . import _subtitulos_render as subs

MARGEN = 76
ANCHO_UTIL = ANCHO_LIENZO - MARGEN * 2
# Dónde empieza cada banda; en negativo, dónde **acaba**, contado desde abajo.
# «baja» no la elige la ficha: la usan por dentro el círculo y la gráfica para
# irse al lado contrario de lo que están señalando, y acaba en 1220, antes de
# donde empieza el titular.
BANDAS = {"arriba": 320, "centro": 820, "baja": -700}
# La chapa va justo debajo de los subtítulos, que en motion son pequeños y van
# arriba (ver plantilla `explica`).
Y_CHAPA = 212
# El titular acaba a 250 del canto de abajo. Dos líneas suyas empiezan sobre
# los 1440, así que nunca pisa la banda «baja».
Y_TITULAR = -250
TITULAR_CUERPO = 88

GROTESCA = "Montserrat ExtraBold"
MONO = ("Menlo", "/System/Library/Fonts/Menlo.ttc", "Courier New Bold.ttf")


@lru_cache(maxsize=192)
def _fuente(cual: str, tam: int):
    from PIL import ImageFont

    if cual == "mono":
        for cand in MONO:
            p = Path(cand) if cand.startswith("/") else subs.buscar_fuente(cand)
            if p and Path(p).exists():
                return ImageFont.truetype(str(p), tam)
    p = subs.buscar_fuente(GROTESCA)
    if p is None:
        raise RuntimeError(f"No encuentro la fuente «{GROTESCA}» para el modo motion")
    return ImageFont.truetype(str(p), tam)


# ── Dibujo con alfa, solo donde hace falta ────────────────────────────────
def _con_alfa(im, caja, alfa, pinta):
    """Pinta sobre `im`, y si va a medio desvanecer, sobre una capa aparte.

    Montar una capa RGBA del tamaño del lienzo en cada fotograma cuesta más que
    dibujar el esquema entero. Como solo las entradas van con alfa —y duran
    medio segundo de los varios que dura una escena—, la mayoría de los cuadros
    se pintan directos y solo los de la entrada pagan una capa, del tamaño de
    lo que entra y no del cuadro.
    """
    from PIL import Image, ImageDraw

    if alfa >= 0.995:
        pinta(ImageDraw.Draw(im), 0, 0)
        return
    if alfa <= 0.004:
        return
    x0, y0, x1, y1 = (round(v) for v in caja)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, x1), min(im.height, y1)
    if x1 <= x0 or y1 <= y0:
        return
    capa = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    pinta(ImageDraw.Draw(capa), -x0, -y0)
    alfa_canal = capa.getchannel("A").point(lambda v: round(v * alfa))
    capa.putalpha(alfa_canal)
    im.paste(capa, (x0, y0), capa)


def _plato(im, caja, alfa: float, r: float) -> None:
    """Oscurece lo que haya detrás del texto, con esquinas redondeadas.

    Sobre una textura bastaría la viñeta, con el texto leyéndose encima. Un
    esquema no es textura —son cajas con sus propias etiquetas—, y un titular
    cruzado por una caja de memoria no se lee ninguno de los dos. El plato no
    pinta un panel: funde lo que hay con el fondo, así que la pieza se sigue
    intuyendo debajo y el texto manda.
    """
    from PIL import Image, ImageDraw

    if alfa <= 0.01:
        return
    x0, y0, x1, y1 = (round(v) for v in caja)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, x1), min(im.height, y1)
    if x1 <= x0 or y1 <= y0:
        return
    trozo = im.crop((x0, y0, x1, y1))
    apagado = Image.blend(trozo, Image.new("RGB", trozo.size, PANEL), min(1.0, alfa))
    mascara = Image.new("L", trozo.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        [0, 0, trozo.width - 1, trozo.height - 1], radius=round(r), fill=255)
    im.paste(apagado, (x0, y0), mascara)


def _medir(d, texto, font, **kw):
    c = d.textbbox((0, 0), texto, font=font, **kw)
    return c[2] - c[0], c[3] - c[1], c[0], c[1]


def _ajustar(d, texto, cual, tam, ancho_max, minimo):
    """La fuente más grande con la que `texto` cabe de una línea.

    Los bloques que se parten en varias líneas usan `_partir`; los que son una
    línea por definición —un rótulo, una cifra— no pueden partirse sin dejar de
    ser lo que son, así que lo que cede es el cuerpo. El tope de palabras de la
    ficha ya evita que esto llegue a letra pequeña: aquí se corrige la palabra
    larga suelta, no una frase metida donde no iba.
    """
    while tam > minimo:
        fuente = _fuente(cual, tam)
        if _medir(d, texto, fuente)[0] <= ancho_max:
            return fuente
        tam -= 2 * (tam // 24 or 1)
    return _fuente(cual, max(minimo, tam))


def _partir(d, texto, font, ancho_max):
    """Parte el texto en líneas que caben. Una tarjeta de cuatro segundos que
    se sale del cuadro no es un detalle de estilo: no se lee."""
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if actual and _medir(d, prueba, font)[0] > ancho_max:
            lineas.append(actual)
            actual = palabra
        else:
            actual = prueba
    if actual:
        lineas.append(actual)
    return lineas


# «titular» no es una banda que se pueda elegir: es el sitio de la capa de
# titulares, y se resuelve con la misma cuenta que las demás.
_Y = {**BANDAS, "titular": Y_TITULAR}


def _y_banda(banda: str, altura: float, s: int) -> float:
    y = _Y.get(banda, BANDAS["centro"])
    return (ALTO_LIENZO + y) * s - altura if y < 0 else y * s


# ── Los bloques ───────────────────────────────────────────────────────────
def _rotulo(im, d0, f, t, s):
    lugar, anio = f["texto"], f.get("apoyo", "")
    fl = _ajustar(d0, lugar, "grotesca", 86 * s, ANCHO_UTIL * s, 44 * s)
    fa = _fuente("mono", 32 * s)
    aw, ah, ax, ay = _medir(d0, lugar, fl)
    alto = ah + (48 * s if anio else 0)
    y = _y_banda(f["banda"], alto, s)
    p = tramo(t, 0.15, 0.5)
    sube = (1 - salida(p)) * 100 * s
    _plato(im, (MARGEN * s - 34 * s, y - 30 * s,
                MARGEN * s + aw + 34 * s, y + alto + 26 * s),
           0.9 * salida(p), 28 * s)

    def pinta(d, ox, oy):
        d.text((MARGEN * s - ax + ox, y + sube - ay + oy), lugar, font=fl, fill=INK)
    _con_alfa(im, (0, y - 20 * s, im.width, y + alto + 40 * s), salida(p), pinta)

    if anio:
        pa = tramo(t, 0.35, 0.6)

        def pinta_anio(d, ox, oy):
            # La monoespaciada entra abriéndose, que es el gesto del rótulo.
            sep = round((1 - salida(pa)) * 18 * s)
            x = MARGEN * s + ox
            for ch in anio:
                d.text((x, y + ah + 16 * s + oy), ch, font=fa, fill=APOYO)
                x += _medir(d, ch, fa)[0] + 10 * s + sep
        _con_alfa(im, (0, y + ah, im.width, y + ah + 70 * s), salida(pa), pinta_anio)


def _vigente(titulares: list[dict], t: float) -> tuple[dict, float] | None:
    """Qué titular toca ahora y cuánto lleva en pantalla.

    Se busca por los tiempos de la frase, no por el orden: un clip se dibuja
    cuadro a cuadro y cada uno pregunta por su instante, sin recordar el
    anterior. Antes del primero no hay nada escrito, que es correcto — la
    escena empieza en el silencio que dejó la anterior.
    """
    for k in range(len(titulares) - 1, -1, -1):
        tt = titulares[k]
        if t >= tt.get("t0", 0.0):
            return tt, t - tt.get("t0", 0.0)
    return None


def capa_titulares(im, d0, titulares: list[dict], t: float, s: int) -> None:
    """El titular de la frase que se está diciendo, abajo y centrado.

    Centrado y no a la izquierda como el resto de los bloques: es la única
    capa que se releva sola, y con el margen izquierdo cada relevo movía el
    bloque de texto de sitio de una forma que se leía como un error.
    """
    vigente = _vigente(titulares or [], t)
    if vigente is None:
        return
    tt, local = vigente
    texto = (tt.get("texto") or "").strip()
    if not texto:
        return
    fuente = _fuente("grotesca", TITULAR_CUERPO * s)
    fuera = {w.lower().strip(" .,") for w in tt.get("enfasis") or []}
    lineas = _partir(d0, texto, fuente, ANCHO_UTIL * s)
    paso = 108 * s
    alto = paso * len(lineas)
    y0 = _y_banda("titular", alto, s)
    # El relevo: los últimos dos décimos se va apagando para que el siguiente
    # no aparezca encima del que todavía se está leyendo.
    dura = tt.get("t1", local + 9.9) - tt.get("t0", 0.0)
    apaga = 1.0 - salida(tramo(local, max(0.0, dura - 0.22), 0.22), 2)

    # El hueco entre dos palabras, medido en la propia fuente. Las palabras se
    # colocan por su tinta —no por su avance— para poder encenderlas una a
    # una, así que el hueco tiene que ser el de tinta a tinta o la línea sale
    # apretada o suelta según qué letras lleve.
    uno = _medir(d0, "a", fuente)[0]
    hueco = max(6 * s, _medir(d0, "a a", fuente)[0] - 2 * uno)

    puestas, ancho = [], 0.0
    for linea in lineas:
        palabras = linea.split()
        anchos = [_medir(d0, w, fuente)[0] for w in palabras]
        # **Todas las palabras de una línea comparten la referencia vertical de
        # la línea.** Restarle a cada una la suya alinea los topes de tinta y
        # no las bases: una palabra sin mayúsculas ni astas sube por encima de
        # sus vecinas y la línea se lee como si estuviera rota. Era lo que
        # pasaba.
        base = _medir(d0, linea, fuente)[3]
        largo = sum(anchos) + hueco * (len(palabras) - 1)
        puestas.append((palabras, anchos, base, largo))
        ancho = max(ancho, largo)

    # Y el titular entra de una pieza, no palabra por palabra. Cada palabra
    # con su propio salto dejaba la frase a cuatro alturas distintas durante el
    # tercio de segundo que dura la entrada, que es justo cuando se empieza a
    # leer. Lo que se escalona es encenderse, no moverse.
    entra = salida(tramo(local, 0.0, 0.3))
    sube = (1 - entra) * 70 * s

    _plato(im, ((ANCHO_LIENZO * s - ancho) / 2 - 40 * s, y0 - 34 * s,
                (ANCHO_LIENZO * s + ancho) / 2 + 40 * s, y0 + alto + 4 * s),
           0.9 * entra * apaga, 30 * s)
    n = 0
    for li, (palabras, anchos, base, largo) in enumerate(puestas):
        x = (ANCHO_LIENZO * s - largo) / 2
        y = y0 + li * paso + sube - base
        for palabra, pw in zip(palabras, anchos):
            p = salida(tramo(local, n * 0.055, 0.22)) * apaga
            px = _medir(d0, palabra, fuente)[2]
            color = ACENTO if palabra.lower().strip(" .,") in fuera else INK

            def pinta(d, ox, oy, x=x, y=y, palabra=palabra, color=color, px=px):
                d.text((x - px + ox, y + oy), palabra, font=fuente, fill=color)
            _con_alfa(im, (x - 10 * s, y0 + li * paso - 30 * s,
                           x + pw + 20 * s, y0 + (li + 1) * paso + 20 * s),
                      p, pinta)
            x += pw + hueco
            n += 1


def chapa(im, d0, texto: str, t: float, s: int) -> None:
    """La píldora de contexto, arriba y quieta toda la escena.

    En versalitas muy espaciadas y en monoespaciada: es la tipografía que en
    este lenguaje significa «dato», y distinguirla del titular de un vistazo
    es justo lo que hace que no compitan.
    """
    texto = (texto or "").strip().upper()
    if not texto:
        return
    f = _fuente("mono", 26 * s)
    sep = 6 * s
    anchos = [_medir(d0, ch, f)[0] + sep for ch in texto]
    th = _medir(d0, texto, f)[1]
    ancho = sum(anchos) - sep + 76 * s
    alto = th + 30 * s
    x0 = (ANCHO_LIENZO * s - ancho) / 2
    y0 = Y_CHAPA * s
    p = salida(tramo(t, 0.05, 0.4))

    def pinta(d, ox, oy):
        _caja_redonda(d, (x0 + ox, y0 + oy, x0 + ancho + ox, y0 + alto + oy),
                      alto / 2, PANEL, FILO, max(1, round(2 * s)))
        r = 5 * s
        cy = y0 + alto / 2 + oy
        d.ellipse([x0 + 26 * s + ox - r, cy - r, x0 + 26 * s + ox + r, cy + r],
                  fill=ACENTO)
        x = x0 + 48 * s + ox
        for ch, w in zip(texto, anchos):
            d.text((x, y0 + 15 * s + oy), ch, font=f, fill=APOYO)
            x += w
    _con_alfa(im, (x0 - 20 * s, y0 - 20 * s, x0 + ancho + 20 * s, y0 + alto + 20 * s),
              p, pinta)


def _cifra(im, d0, f, t, s):
    fn = _ajustar(d0, f["texto"], "grotesca", 250 * s, ANCHO_UTIL * s, 110 * s)
    fu = _fuente("mono", 30 * s)
    nw, nh, nx, ny = _medir(d0, f["texto"], fn)
    unidad = f.get("apoyo", "").upper()
    alto = nh + (58 * s if unidad else 0)
    y = _y_banda(f["banda"], alto, s)
    p = salida(tramo(t, 0.15, 0.45))
    sube = (1 - p) * 90 * s
    _plato(im, (MARGEN * s - 34 * s, y - 40 * s,
                MARGEN * s + max(nw, _medir(d0, unidad, fu)[0]) + 34 * s,
                y + alto + 22 * s), 0.9 * p, 30 * s)

    def pinta(d, ox, oy):
        d.text((MARGEN * s - nx + ox, y + sube - ny + oy), f["texto"], font=fn, fill=ACENTO)
    _con_alfa(im, (0, y - 30 * s, im.width, y + nh + 60 * s), p, pinta)

    if unidad:
        pu = tramo(t, 0.45, 0.4)

        def pinta_u(d, ox, oy):
            d.text((MARGEN * s + ox, y + nh + 24 * s + oy), unidad, font=fu, fill=APOYO)
        _con_alfa(im, (0, y + nh, im.width, y + nh + 80 * s), pu, pinta_u)


def _caja_redonda(d, caja, r, relleno, filo=None, grosor=2):
    d.rounded_rectangle(caja, radius=r, fill=relleno, outline=filo, width=grosor)


def _pildora(im, d0, f, t, s, esc, cam, ancla):
    if ancla is None:
        return
    ax, ay = ancla
    fuente = _fuente("grotesca", 30 * s)
    tw, th, tx, ty = _medir(d0, f["texto"], fuente)
    p = rebote(tramo(t, 0.25, 0.42))
    # Crece desde su punto: la píldora señala, no flota. Hacia la derecha salvo
    # que allí se saliera del cuadro, porque el ancla es un sitio del mundo y el
    # mundo no sabe dónde está el margen.
    ancho = tw + 52 * s
    alto = th + 28 * s
    borde = ax + 30 * s
    hacia = 1 if borde + ancho <= im.width - MARGEN * s / 2 else -1
    if hacia < 0:
        # El ancla viene en el canto derecho de la pieza. Creciendo hacia la
        # izquierda desde ahí, la píldora se mete dentro y tapa el nombre, así
        # que se cambia de canto y sale por el lado contrario.
        pieza = (getattr(esc, "piezas", None) or {}).get(f.get("foco", ""))
        if pieza is not None:
            ax -= pieza["w"] * cam["z"] * s
        borde = ax - 30 * s
    escala = max(0.01, p)

    def pinta(d, ox, oy):
        crece = borde + hacia * ancho * escala
        izq, der = min(borde, crece), max(borde, crece)
        _caja_redonda(d, (izq + ox, ay - alto * escala / 2 + oy,
                          der + ox, ay + alto * escala / 2 + oy),
                      alto * escala / 2, PANEL, FILO, max(1, round(2 * s)))
        r = 8 * s
        d.ellipse([ax - r + ox, ay - r + oy, ax + r + ox, ay + r + oy], fill=INK)
        if p > 0.55:
            x = (borde if hacia > 0 else borde - ancho) + 26 * s - tx
            d.text((x + ox, ay - th / 2 - ty + oy), f["texto"], font=fuente, fill=INK)
    izq = borde - ancho if hacia < 0 else ax - 30 * s
    der = borde + ancho if hacia > 0 else ax + 30 * s
    _con_alfa(im, (izq - 20 * s, ay - alto, der + 20 * s, ay + alto),
              min(1.0, tramo(t, 0.25, 0.3)), pinta)


def _radio_circulo(esc, foco: str) -> tuple[float, float]:
    """Los dos radios del óvalo que rodea la pieza, en unidades de mundo.

    Con un radio fijo era un aro en mitad de la pieza, tapándole el nombre y
    sin dejar claro qué se señalaba. Y con un círculo redondo alrededor de un
    banco ancho y bajo, el aro se estiraba hasta las piezas de al lado: por eso
    cada eje lleva el suyo.
    """
    p = (getattr(esc, "piezas", None) or {}).get(foco)
    if not p:
        return 112.0, 112.0
    return (min(460.0, max(90.0, p["w"] / 2 + 26)),
            min(460.0, max(90.0, p["h"] / 2 + 26)))


def _circulo(im, d0, f, t, s, esc, cam, ancla):
    if ancla is None:
        return
    ax, ay = ancla
    rx_m, ry_m = _radio_circulo(esc, f.get("foco", ""))
    rx, ry = rx_m * cam["z"] * s, ry_m * cam["z"] * s
    fuente = _fuente("grotesca", 40 * s)
    fs = _fuente("mono", 25 * s)
    lineas = _partir(d0, f["texto"], fuente, 560 * s)
    apoyo = f.get("apoyo", "")
    alto_caja = len(lineas) * 50 * s + (38 * s if apoyo else 0) + 40 * s
    # La banda de este bloque no la decide la ficha: se decide aquí, con el
    # ancla ya proyectada. La ficha se escribió sin saber en qué parte de la
    # pantalla iba a caer el círculo, y una etiqueta encima de lo que el
    # círculo está rodeando tapa justo lo que se quería señalar.
    cy = _y_banda("baja" if ay < im.height * 0.5 else "arriba", alto_caja, s)
    cx = MARGEN * s
    destino = (cx + 580 * s, cy + 20 * s)

    pc = entrada_salida(tramo(t, 0.2, 0.7))
    if pc > 0.01:
        def pinta_c(d, ox, oy):
            # El arco se dibuja creciendo: es el gesto de rodear algo a mano.
            d.arc([ax - rx + ox, ay - ry + oy, ax + rx + ox, ay + ry + oy],
                  -90, -90 + 360 * pc, fill=INK, width=max(2, round(6 * s)))
        _con_alfa(im, (ax - rx - 20 * s, ay - ry - 20 * s,
                       ax + rx + 20 * s, ay + ry + 20 * s), 1.0, pinta_c)

    pg = salida(tramo(t, 0.6, 0.35), 2)
    if pg > 0.01:
        vx, vy = destino[0] - ax, destino[1] - ay
        dd = math.hypot(vx, vy) or 1
        # El tirador arranca del óvalo, no del centro: se resuelve en qué
        # punto del borde lo corta la dirección en la que sale.
        k = 1 / math.hypot(vx / dd / rx, vy / dd / ry)
        x0, y0 = ax + vx / dd * k, ay + vy / dd * k
        x1, y1 = x0 + (destino[0] - x0) * pg, y0 + (destino[1] - y0) * pg

        def pinta_g(d, ox, oy):
            d.line([(x0 + ox, y0 + oy), (x1 + ox, y1 + oy)], fill=INK,
                   width=max(1, round(4 * s)))
        _con_alfa(im, (min(x0, x1) - 10 * s, min(y0, y1) - 10 * s,
                       max(x0, x1) + 10 * s, max(y0, y1) + 10 * s), 1.0, pinta_g)

    pe = salida(tramo(t, 0.85, 0.4), 3)
    if pe > 0.01:
        sube = (1 - pe) * 40 * s

        def pinta_e(d, ox, oy):
            caja = (cx + ox, cy + sube + oy, cx + 620 * s + ox, cy + sube + alto_caja + oy)
            d.rectangle(caja, fill=PANEL, outline=FILO, width=max(1, round(2 * s)))
            d.rectangle([caja[0], caja[1], caja[0] + 6 * s, caja[3]], fill=INK)
            y = caja[1] + 20 * s
            for linea in lineas:
                d.text((caja[0] + 26 * s, y), linea, font=fuente, fill=INK)
                y += 50 * s
            if apoyo:
                d.text((caja[0] + 26 * s, y + 4 * s), apoyo.upper(), font=fs, fill=APOYO)
        _con_alfa(im, (cx - 10 * s, cy - 10 * s, cx + 640 * s, cy + alto_caja + 60 * s),
                  pe, pinta_e)


# Doce medidas que suben y casi no vuelven. La serie es fija a propósito: la
# gráfica ilustra la forma de lo que se cuenta, y un dato de verdad tendría que
# venir del guion, no de aquí.
SERIE = (0.18, 0.26, 0.31, 0.44, 0.58, 0.73, 0.86, 0.94, 0.90, 0.88, 0.85, 0.87)


def _grafica(im, d0, f, t, s):
    fc = _fuente("mono", 25 * s)
    fn = _fuente("mono", 28 * s)
    ancho, alto = ANCHO_UTIL * s, 300 * s
    y0 = _y_banda(f["banda"], alto, s)
    x0 = MARGEN * s
    pp = salida(tramo(t, 0.15, 0.45), 3)
    sube = (1 - pp) * 70 * s

    ejes_y = y0 + sube + alto - 40 * s
    ejes_x = x0 + 46 * s
    ancho_serie, alto_serie = ancho - 92 * s, alto - 120 * s
    puntos = [(ejes_x + i * ancho_serie / (len(SERIE) - 1), ejes_y - v * alto_serie)
              for i, v in enumerate(SERIE)]
    pt = entrada_salida(tramo(t, 0.55, 1.1))
    # Hasta dónde ha llegado el trazo: la punta avanza por la curva.
    hasta = pt * (len(SERIE) - 1)
    dibujados = puntos[:int(hasta) + 1]
    if int(hasta) + 1 < len(puntos):
        a, b = puntos[int(hasta)], puntos[int(hasta) + 1]
        q = hasta - int(hasta)
        dibujados.append((a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q))

    def pinta(d, ox, oy):
        caja = (x0 + ox, y0 + sube + oy, x0 + ancho + ox, y0 + sube + alto + oy)
        _caja_redonda(d, caja, 18 * s, PANEL, FILO, max(1, round(2 * s)))
        d.text((caja[0] + 30 * s, caja[1] + 26 * s), f["texto"].upper(), font=fc, fill=APOYO)
        pe = salida(tramo(t, 0.3, 0.45), 2)
        if pe > 0.01:
            d.line([(ejes_x + ox, caja[1] + 80 * s + oy), (ejes_x + ox, ejes_y + oy),
                    (ejes_x + ancho_serie * pe + ox, ejes_y + oy)],
                   fill=(90, 92, 99), width=max(1, round(3 * s)))
        if len(dibujados) > 1:
            d.line([(x + ox, y + oy) for x, y in dibujados], fill=LIMA,
                   width=max(2, round(6 * s)), joint="curve")
            px, py = dibujados[-1]
            r = 11 * s
            d.ellipse([px - r + ox, py - r + oy, px + r + ox, py + r + oy], fill=LIMA)
        apoyo = f.get("apoyo", "")
        if apoyo and t > 1.5:
            aw = _medir(d, apoyo, fn)[0]
            d.text((caja[2] - 34 * s - aw, caja[1] + 28 * s), apoyo, font=fn, fill=LIMA)
    _con_alfa(im, (x0 - 20 * s, y0 - 20 * s, x0 + ancho + 20 * s, y0 + alto + 80 * s),
              pp, pinta)


def _lista(im, d0, f, t, s):
    """Las filas que se enumeran, entrando una a una.

    Es el bloque que sostiene un vídeo que promete «tres cosas» y luego las
    dice: sin él, el espectador llega al final sin saber por cuál va. La chapa
    de la derecha es lo pequeño que remata cada fila —una licencia, un precio,
    un veredicto— y puede faltar.
    """
    filas = [fl for fl in (f.get("filas") or []) if (fl.get("texto") or "").strip()]
    if not filas:
        return
    fn = _fuente("mono", 30 * s)
    fc = _fuente("mono", 24 * s)
    paso = 96 * s
    alto = paso * len(filas) - 18 * s
    y0 = _y_banda(f["banda"], alto, s)
    x0, ancho = MARGEN * s, ANCHO_UTIL * s

    for k, fila in enumerate(filas):
        # Entran escalonadas, no todas a la vez: así se lee el orden, que es
        # para lo que está la lista.
        pf = salida(tramo(t, 0.2 + k * 0.22, 0.4), 3)
        if pf <= 0.01:
            continue
        y = y0 + k * paso
        corre = (1 - pf) * 60 * s
        texto = (fila.get("texto") or "").strip()
        ft = _ajustar(d0, texto, "grotesca", 46 * s, ancho - 230 * s, 26 * s)
        chapita = (fila.get("chapa") or "").strip().upper()

        def pinta(d, ox, oy, y=y, corre=corre, texto=texto, ft=ft,
                  chapita=chapita, k=k):
            caja = (x0 + corre + ox, y + oy, x0 + ancho + corre + ox,
                    y + paso - 18 * s + oy)
            _caja_redonda(d, caja, 20 * s, PANEL, FILO, max(1, round(2 * s)))
            # El número en su cuadrado: es el ordinal de la fila, no parte del
            # texto, y mezclarlos los hace ilegibles a los dos.
            cuad = (caja[0] + 18 * s, caja[1] + 16 * s,
                    caja[0] + 64 * s, caja[3] - 16 * s)
            _caja_redonda(d, cuad, 12 * s, mezcla(PANEL, ACENTO, 0.22), None, 0)
            nw, nh, nx, ny = _medir(d, str(k + 1), fn)
            d.text(((cuad[0] + cuad[2]) / 2 - nw / 2 - nx,
                    (cuad[1] + cuad[3]) / 2 - nh / 2 - ny), str(k + 1),
                   font=fn, fill=INK)
            tw, th, tx, ty = _medir(d, texto, ft)
            d.text((cuad[2] + 26 * s - tx, (caja[1] + caja[3]) / 2 - th / 2 - ty),
                   texto, font=ft, fill=INK)
            if chapita:
                cw, ch, cx, cy = _medir(d, chapita, fc)
                der = caja[2] - 20 * s
                _caja_redonda(d, (der - cw - 34 * s, (caja[1] + caja[3]) / 2 - ch,
                                  der, (caja[1] + caja[3]) / 2 + ch),
                              ch, None, FILO, max(1, round(2 * s)))
                d.text((der - cw - 17 * s - cx,
                        (caja[1] + caja[3]) / 2 - ch / 2 - cy), chapita,
                       font=fc, fill=APOYO)
        _con_alfa(im, (x0 - 20 * s, y - 20 * s, x0 + ancho + 80 * s,
                       y + paso + 20 * s), pf, pinta)


def _ordinal(im, d0, f, t, s):
    """El numeral de orden, enorme y pegado al margen.

    No es la CIFRA: la cifra es un dato del guion y va en el acento; esto es
    por dónde vamos —el tercero de cinco— y va en tinta, grande y apagado,
    para que se lea sin competir con el titular.
    """
    numero = re.sub(r"[^0-9]", "", f.get("texto") or "") or "1"
    fn = _fuente("grotesca", 300 * s)
    fo = _fuente("grotesca", 140 * s)
    nw, nh, nx, ny = _medir(d0, numero, fn)
    y = _y_banda(f["banda"], nh, s)
    p = salida(tramo(t, 0.1, 0.5), 3)
    sube = (1 - p) * 70 * s

    def pinta(d, ox, oy):
        d.text((MARGEN * s - nx + ox, y + sube - ny + oy), numero, font=fn, fill=INK)
        ow, oh, ox2, oy2 = _medir(d, "\u00b0", fo)
        d.text((MARGEN * s + nw + 10 * s - ox2 + ox, y + sube - oy2 + oy),
               "\u00b0", font=fo, fill=ACENTO)
    _con_alfa(im, (0, y - 40 * s, im.width, y + nh + 60 * s), p * 0.92, pinta)


_BLOQUES = {"ROTULO": _rotulo, "CIFRA": _cifra, "GRAFICA": _grafica,
            "LISTA": _lista, "ORDINAL": _ordinal}
_ANCLADOS = {"PILDORA": _pildora, "CIRCULO": _circulo}


def dibujar(im, ficha: dict, esc, cam: dict, t: float, s: int = 2) -> None:
    """Pinta las tres capas de texto sobre el fotograma ya dibujado.

    En este orden y no en otro: el bloque señala algo del esquema y vive con
    él; la chapa y el titular son el marco del vídeo y van por encima de todo,
    porque si un bloque los tapara no habría dónde leer de qué va la toma.
    """
    from PIL import ImageDraw

    d0 = ImageDraw.Draw(im)
    _bloque(im, d0, ficha, esc, cam, t, s)
    chapa(im, d0, ficha.get("chapa", ""), t, s)
    capa_titulares(im, d0, ficha.get("titulares") or [], t, s)


def _bloque(im, d0, ficha: dict, esc, cam: dict, t: float, s: int) -> None:
    bloque = ficha["bloque"]
    if bloque not in _BLOQUES and bloque not in _ANCLADOS:
        return                      # NADA: la toma la cuentan esquema y titular
    sitio = None
    if ficha.get("ancla"):
        sitio = esc.proyectar(cam, *ficha["ancla"], s)
    if bloque in _BLOQUES:
        if bloque == "GRAFICA" and sitio is not None:
            # La gráfica es una placa opaca de un tercio de pantalla, y la
            # ficha eligió su banda sin saber dónde iba a caer la pieza. Se
            # decide aquí, con la pieza ya proyectada: la placa se va al lado
            # contrario para no enterrar aquello de lo que habla.
            ficha = {**ficha,
                     "banda": "baja" if sitio[1] < im.height * 0.5 else "arriba"}
        _BLOQUES[bloque](im, d0, ficha, t, s)
        return
    # Las ancladas necesitan saber dónde cae su sitio en este fotograma, y no
    # se dibujan si ese sitio se ha ido del cuadro.
    ancla = None
    if sitio is not None:
        x, y = sitio
        if -260 * s < x < im.width + 260 * s and -140 * s < y < im.height + 140 * s:
            ancla = (x, y)
    _ANCLADOS[bloque](im, d0, ficha, t, s, esc, cam, ancla)
