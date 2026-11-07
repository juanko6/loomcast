"""La composición de una escena de motion: qué se dibuja y qué hace.

Cada escena trae su propia composición y se dibuja sobre negro. No hay
decorado compartido: lo que une dos escenas seguidas es que la segunda diga que
continúa, y entonces hereda las piezas de la anterior (lo hace `motion.py`) y
solo cambian la cámara y lo que se anima. Así el esquema se va montando
mientras se narra en vez de estar entero desde el primer segundo.

**La colocación la calcula el código, no el modelo.** El LLM dice qué piezas
hay y qué va conectado con qué; de ahí sale el reparto por filas, y el hueco
entre dos filas lo pone el **coste** del vínculo. Eso es lo que hace que «la
RAM está lejos» se vea: no es una metáfora escrita en la tarjeta, es un hueco
grande y unos paquetes que tardan en cruzarlo. Si las coordenadas las pusiera
el modelo, la mitad de los vídeos saldrían con las cajas pisándose y no hay
forma de revisar eso a ojo.

**Lo lento es lento de verdad.** Un estado no cambia el dibujo por un dibujo
distinto: cambia el canto, el pulso y lo que tarda. La RAM «lenta» no lleva una
tortuga encima, tarda dos segundos en contestar; la caché «caliente» respira en
naranja. Es lo que se puede dibujar sin ilustrador, y en movimiento se entiende
mejor que el chiste.

Las medidas de aquí son del **mundo**, no de la pantalla: una pieza está en un
sitio y la pantalla es donde ese sitio cae en este fotograma (ver
`_motion_lienzo.Mundo`). Todo se pinta al doble y se reduce, así que los
grosores se multiplican por `s`.
"""
import math

from ._motion_bloques import _ajustar, _fuente, _medir
from ._motion_lienzo import (ACENTO, ALERTA, ALTO_LIENZO, ANCHO_LIENZO, APOYO,
                             CALOR, FILO, FONDO, INK, LIMA, PANEL, TENUE,
                             Mundo, entrada_salida, mezcla, respira, salida,
                             tramo)

TIPOS = ("chip", "banco", "caja", "disco", "nodo", "terminal", "navegador")
ESTADOS = ("normal", "veloz", "lento", "caliente", "lleno", "vacio", "fallando")
ANIMACIONES = ("flujo", "buscar", "fallo", "llenar", "latido", "espera",
               "comparar", "teclear", "nada")
# Las dos ventanas: la pieza que trae a la pantalla algo que existe de verdad
# —el comando que se teclea, la dirección a la que se va—. Es lo que separa un
# plano que informa de uno que decora, y por eso lo que llevan dentro sale del
# guion y no de aquí.
VENTANAS = ("terminal", "navegador")
COSTES = ("corto", "medio", "largo")
FONDOS = ("negro", "rejilla")

MAX_PIEZAS = 6
MAX_RANURAS = 8
# Lo que cabe dentro de una ventana sin que la letra baje de lo legible en un
# móvil. Cinco líneas son un comando y su respuesta, que es toda la historia
# que una toma de cuatro segundos puede contar.
MAX_LINEAS = 5
# Lo que cabe a lo ancho de una ventana en monoespaciada sin salirse. Un
# comando más largo que esto se parte en dos líneas al escribirlo, no se
# recorta: lo que no se lee entero no sirve de nada.
MAX_COLUMNAS = 40

# El hueco entre dos filas lo decide el coste del vínculo que las une: es la
# distancia, y es lo único que hace que «lejos» se vea.
HUECO_FILA = {"corto": 80, "medio": 160, "largo": 300}
HUECO_COL = 80
MARGEN_MUNDO = 90
# Un poco más de aire arriba y abajo que a los lados, para que una pieza no
# acabe pegada al canto del cuadro. El sitio de la tarjeta no se reserva aquí:
# lo reserva la cámara (`AIRE_TARJETA`), y hacerlo en los dos sitios encoge el
# esquema hasta que no se le ven las ranuras.
MARGEN_ALTO = 80
# Lo que tarda un paquete en cruzar un vínculo, por coste. Un vínculo largo no
# es solo más largo: además se cruza despacio.
CRUCE_S = {"corto": 0.5, "medio": 1.0, "largo": 2.1}

ESTADO_CANTO = {"normal": FILO, "veloz": LIMA, "lento": (62, 66, 76),
                "caliente": CALOR, "lleno": ACENTO, "vacio": FILO,
                "fallando": ALERTA}
# Cada cuánto respira el canto de una pieza según cómo esté. El que no respira
# está quieto, que también dice algo.
ESTADO_PULSO = {"veloz": 0.55, "lento": 2.6, "caliente": 0.9, "fallando": 0.34}


def _norm(caja):
    x0, y0, x1, y1 = caja
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _tamano(p: dict) -> tuple[float, float]:
    """Lo que ocupa cada tipo de pieza en el mundo."""
    tipo = p["tipo"]
    if tipo == "chip":
        return 480.0, 300.0
    if tipo == "banco":
        return 660.0, 92.0 + p["ranuras"] * 40.0
    if tipo == "caja":
        return 560.0, 150.0
    if tipo == "disco":
        return 380.0, 340.0
    if tipo == "terminal":
        return 800.0, 108.0 + max(1, len(p.get("lineas") or [])) * 48.0
    if tipo == "navegador":
        return 800.0, 190.0 + max(1, len(p.get("lineas") or [])) * 46.0
    return 220.0, 180.0            # nodo


def _capas(orden: list[str], vinculos: list[dict]) -> dict[str, int]:
    """En qué fila va cada pieza, deducido de los vínculos.

    Lo que no cuelga de nada abre fila (capa 0) y cada vínculo empuja al
    destino una fila más abajo que su origen. Con un ciclo no hay raíces y
    todas acaban en la misma fila: sale apretado, pero sale.
    """
    padres = {v["a"] for v in vinculos}
    capa = {pid: 0 for pid in orden if pid not in padres}
    for _ in range(len(orden) + 1):
        movido = False
        for v in vinculos:
            if v["de"] in capa:
                nueva = capa[v["de"]] + 1
                if nueva > capa.get(v["a"], -1):
                    capa[v["a"]], movido = nueva, True
        if not movido:
            break
    suelta = max(capa.values(), default=-1) + 1
    for pid in orden:
        capa.setdefault(pid, suelta)
    return capa


class Escenario(Mundo):
    """Las piezas de una escena, colocadas, y lo que hacen mientras dura."""

    def __init__(self, comp: dict, dur: float = 4.0):
        self.fondo = comp.get("fondo") if comp.get("fondo") in FONDOS else "negro"
        self.animacion = dict(comp.get("animacion") or {"tipo": "nada"})
        self.dur = max(0.4, dur)
        self.piezas = {}
        self.orden = []
        for p in comp.get("piezas") or []:
            # Con valores por defecto aquí también, y no solo en el revisor: lo
            # que llega es un JSON de la base, y una ficha a la que le falte
            # una clave tiene que salir fea, no reventar el render.
            pid = str(p.get("id") or f"p{len(self.orden) + 1}")
            self.piezas[pid] = {
                "id": pid, "tipo": p.get("tipo", "caja"),
                "nombre": p.get("nombre", ""),
                "ranuras": int(p.get("ranuras") or 0),
                "llenas": int(p.get("llenas") or 0),
                "estado": p.get("estado", "normal"),
                "lineas": [str(l) for l in (p.get("lineas") or [])][:MAX_LINEAS],
            }
            self.orden.append(pid)
        self.vinculos = [
            {"de": v["de"], "a": v["a"], "coste": v.get("coste", "medio")}
            for v in (comp.get("vinculos") or [])
            if v.get("de") in self.piezas and v.get("a") in self.piezas
        ]
        self.foco = comp.get("foco") if comp.get("foco") in self.piezas else (
            self.orden[-1] if self.orden else "")
        self._colocar()

    # ── Colocación ────────────────────────────────────────────────────────
    def _colocar(self) -> None:
        """Reparte las piezas por filas y deja el mundo medido."""
        if not self.orden:
            self.ancho = self.alto = 600.0
            return
        capa = _capas(self.orden, self.vinculos)
        filas: dict[int, list[str]] = {}
        for pid in self.orden:
            filas.setdefault(capa[pid], []).append(pid)

        for pid in self.orden:
            self.piezas[pid]["w"], self.piezas[pid]["h"] = _tamano(self.piezas[pid])

        # El hueco que precede a una fila es el del vínculo más caro que entra
        # en ella: si algo llega de lejos, la fila entera se va abajo.
        y = 0.0
        for n in sorted(filas):
            if n > 0:
                costes = [v.get("coste", "medio") for v in self.vinculos
                          if v["a"] in filas[n]]
                peor = max(costes, key=lambda c: HUECO_FILA.get(c, HUECO_FILA["medio"]),
                           default="medio")
                y += HUECO_FILA.get(peor, HUECO_FILA["medio"])
            fila = filas[n]
            ancho = sum(self.piezas[i]["w"] for i in fila) + HUECO_COL * (len(fila) - 1)
            x = -ancho / 2
            alta = max(self.piezas[i]["h"] for i in fila)
            for pid in fila:
                p = self.piezas[pid]
                p["x"], p["y"] = x, y + (alta - p["h"]) / 2
                x += p["w"] + HUECO_COL
            y += alta

        x0 = min(p["x"] for p in self.piezas.values()) - MARGEN_MUNDO
        y0 = -MARGEN_ALTO
        for p in self.piezas.values():
            p["x"] -= x0
            p["y"] -= y0
        self.ancho = max(p["x"] + p["w"] for p in self.piezas.values()) + MARGEN_MUNDO
        self.alto = y + MARGEN_ALTO * 2

    @property
    def encuadre(self) -> float:
        """El zoom al que la escena entera cabe en el cuadro."""
        return min(ANCHO_LIENZO / self.ancho, ALTO_LIENZO / self.alto) * 0.96

    def _centro(self, cam: dict) -> tuple[float, float]:
        """Aquí la cámara va donde quiere, sin el tope del mundo.

El tope del mundo existe para no enseñar el borde de un decorado, y un
        esquema no tiene decorado: está sobre negro, así que fuera no hay nada
        que enseñar. En cambio el tope sí hacía daño: con una pieza arriba del
        todo, acercarse a ella la dejaba a un palmo del centro porque la cámara
        no podía bajar más.
        """
        return cam["x"], cam["y"]

    def centro(self, pid: str = "") -> tuple[float, float]:
        p = self.piezas.get(pid)
        if p is None:
            return self.ancho / 2, self.alto / 2
        return p["x"] + p["w"] / 2, p["y"] + p["h"] / 2

    def ancla(self, pid: str = "", borde: bool = False) -> tuple[float, float]:
        """El sitio del mundo al que se engancha una anotación.

        En el borde para la píldora, que crece hacia un lado y taparía el
        nombre de la pieza si se clavara en el medio; en el centro para el
        círculo, que es lo que la rodea.
        """
        cx, cy = self.centro(pid or self.foco)
        p = self.piezas.get(pid or self.foco)
        if borde and p is not None:
            return cx + p["w"] / 2, cy
        return cx, cy

    # ── Geometría de las piezas ───────────────────────────────────────────
    def ranura(self, pid: str, k: int) -> tuple[float, float, float, float]:
        """La caja (mundo) de la ranura k de un banco."""
        p = self.piezas[pid]
        return (p["x"] + 26, p["y"] + 60 + k * 40, p["w"] - 52, 28)

    def ruta(self, de: str, a: str) -> tuple[tuple, tuple] | None:
        """De dónde a dónde va un paquete entre dos piezas, ya recortado a sus
        cantos: un paquete que sale del centro de una caja sale de dentro."""
        if de not in self.piezas or a not in self.piezas:
            return None
        x0, y0 = self.centro(de)
        x1, y1 = self.centro(a)
        dx, dy = x1 - x0, y1 - y0
        if not dx and not dy:
            return None

        def fuera(pid, sx, sy, vx, vy):
            p = self.piezas[pid]
            tx = (p["w"] / 2) / abs(vx) if vx else math.inf
            ty = (p["h"] / 2) / abs(vy) if vy else math.inf
            t = min(tx, ty)
            return sx + vx * t, sy + vy * t

        return (fuera(de, x0, y0, dx, dy), fuera(a, x1, y1, -dx, -dy))

    def coste(self, de: str, a: str) -> str:
        for v in self.vinculos:
            if v["de"] == de and v["a"] == a:
                return v.get("coste", "medio")
        return "medio"

    def _vinculo_largo(self) -> dict | None:
        if not self.vinculos:
            return None
        return max(self.vinculos,
                   key=lambda v: CRUCE_S.get(v.get("coste", "medio"), 1.0))

    # ── Pintar ────────────────────────────────────────────────────────────
    def pintar(self, d, cam: dict, t: float, s: int = 2) -> None:
        z = cam["z"] * s
        P = lambda wx, wy: self.proyectar(cam, wx, wy, s)        # noqa: E731

        if self.fondo == "rejilla":
            self._rejilla(d, cam, s)
        for v in self.vinculos:
            self._vinculo(d, P, z, s, v, t)
        for pid in self.orden:
            self._pieza(d, P, z, s, pid, t)
        self._animar(d, P, z, s, t)

    def _rejilla(self, d, cam: dict, s: int) -> None:
        """Una retícula apenas visible. Sobre negro puro un movimiento de
        cámara no se ve: no hay nada contra lo que moverse.

        Se dibuja sobre lo que se ve ahora mismo, no sobre el mundo: si la
        cámara se asoma fuera de las piezas, lo que no puede verse es dónde
        se acaba la rejilla.
        """
        paso = 150
        grosor = max(1, round(1.4 * cam["z"] * s))
        ancho, alto = ANCHO_LIENZO / cam["z"], ALTO_LIENZO / cam["z"]
        x0 = (cam["x"] - ancho / 2) // paso * paso
        y0 = (cam["y"] - alto / 2) // paso * paso
        for k in range(int(ancho / paso) + 2):
            x = x0 + k * paso
            d.line([self.proyectar(cam, x, y0, s),
                    self.proyectar(cam, x, y0 + alto + paso, s)],
                   fill=TENUE, width=grosor)
        for k in range(int(alto / paso) + 2):
            y = y0 + k * paso
            d.line([self.proyectar(cam, x0, y, s),
                    self.proyectar(cam, x0 + ancho + paso, y, s)],
                   fill=TENUE, width=grosor)

    def _vinculo(self, d, P, z, s, v: dict, t: float) -> None:
        ruta = self.ruta(v["de"], v["a"])
        if ruta is None:
            return
        (x0, y0), (x1, y1) = ruta
        a, b = P(x0, y0), P(x1, y1)
        largo = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
        # A trazos, y los trazos no se mueven: lo que se mueve son los paquetes.
        # Un vínculo largo lleva el trazo más corto, que es como se dibuja «esto
        # cuesta» en un esquema.
        paso = (26 if v.get("coste") == "largo" else 40) * z
        ux, uy = (b[0] - a[0]) / largo, (b[1] - a[1]) / largo
        n = int(largo / paso)
        grosor = max(1, round((5 if v.get("coste") == "corto" else 3) * z))
        for k in range(n):
            p0 = (a[0] + ux * k * paso, a[1] + uy * k * paso)
            p1 = (p0[0] + ux * paso * 0.55, p0[1] + uy * paso * 0.55)
            d.line([p0, p1], fill=mezcla(FONDO, INK, 0.22), width=grosor)

    def _canto(self, pid: str, t: float) -> tuple:
        """De qué color está el canto de una pieza en este instante."""
        p = self.piezas[pid]
        estado = p.get("estado", "normal")
        color = ESTADO_CANTO.get(estado, FILO)
        periodo = ESTADO_PULSO.get(estado)
        if self.animacion.get("tipo") == "latido" and self.animacion.get("en") == pid:
            color, periodo = LIMA, 0.8
        if periodo is None:
            return color
        if estado == "fallando":
            # El fallo parpadea, no respira: es un aviso.
            return color if (t % periodo) < periodo / 2 else mezcla(FONDO, color, 0.3)
        return mezcla(mezcla(FONDO, color, 0.45), color, respira(t, periodo))

    def _pieza(self, d, P, z, s, pid: str, t: float) -> None:
        p = self.piezas[pid]
        x, y, w, h = p["x"], p["y"], p["w"], p["h"]
        caja = _norm([*P(x, y), *P(x + w, y + h)])
        canto = self._canto(pid, t)
        grosor = max(1, round(3 * z))
        radio = max(2, round(18 * z))

        if p.get("estado") == "caliente":
            # El halo es lo que se ve antes que el color del canto: una pieza
            # que se calienta se nota con el rabillo del ojo.
            halo = mezcla(FONDO, CALOR, 0.10 + 0.16 * respira(t, 0.9))
            g = 16 * z
            d.rounded_rectangle([caja[0] - g, caja[1] - g, caja[2] + g, caja[3] + g],
                                radius=radio + g, fill=halo)

        if p["tipo"] == "disco":
            self._disco(d, caja, canto, grosor)
        elif p["tipo"] == "nodo":
            d.ellipse(caja, fill=PANEL, outline=canto, width=grosor)
        else:
            d.rounded_rectangle(caja, radius=radio, fill=PANEL,
                                outline=canto, width=grosor)

        if p["tipo"] in VENTANAS:
            self._ventana(d, caja, p, canto, z, t)
            return
        if p["tipo"] == "chip":
            self._patillas(d, caja, canto, z)
        if p["tipo"] == "banco":
            self._ranuras(d, P, z, pid, t)
        self._nombre(d, caja, p, z, s)

    def _disco(self, d, caja, canto, grosor) -> None:
        d.ellipse(caja, fill=PANEL, outline=canto, width=grosor)
        for k in (0.62, 0.3):
            w, h = (caja[2] - caja[0]) * k / 2, (caja[3] - caja[1]) * k / 2
            cx, cy = (caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2
            d.ellipse([cx - w, cy - h, cx + w, cy + h], outline=canto, width=grosor)

    def _patillas(self, d, caja, canto, z) -> None:
        """Las patas del chip. Es lo que lo hace un procesador y no una caja."""
        largo, grosor = 16 * z, max(1, round(5 * z))
        for k in range(4):
            q = 0.26 + 0.16 * k
            xx = caja[0] + (caja[2] - caja[0]) * q
            yy = caja[1] + (caja[3] - caja[1]) * q
            d.line([(xx, caja[1] - largo), (xx, caja[1])], fill=canto, width=grosor)
            d.line([(xx, caja[3]), (xx, caja[3] + largo)], fill=canto, width=grosor)
            d.line([(caja[0] - largo, yy), (caja[0], yy)], fill=canto, width=grosor)
            d.line([(caja[2], yy), (caja[2] + largo, yy)], fill=canto, width=grosor)

    def _ranuras(self, d, P, z, pid: str, t: float) -> None:
        p = self.piezas[pid]
        llenas = self._llenas(pid, t)
        color = LIMA if p.get("estado") == "veloz" else ACENTO
        for k in range(p["ranuras"]):
            rx, ry, rw, rh = self.ranura(pid, k)
            caja = _norm([*P(rx, ry), *P(rx + rw, ry + rh)])
            radio = max(1, round(6 * z))
            if k < llenas:
                d.rounded_rectangle(caja, radius=radio, fill=color)
            else:
                d.rounded_rectangle(caja, radius=radio, outline=TENUE,
                                    width=max(1, round(2 * z)))

    def _llenas(self, pid: str, t: float) -> int:
        """Cuántas ranuras están ocupadas ahora. Con `llenar` se van ocupando
        durante la escena; sin animación, las que diga la ficha."""
        p = self.piezas[pid]
        n = p["ranuras"]
        if p.get("estado") == "lleno":
            return n
        if p.get("estado") == "vacio":
            return 0
        a = self.animacion
        if a.get("tipo") == "llenar" and a.get("en") == pid and n:
            desde = p.get("llenas", 0)
            hueco = max(0.0, self.dur - 0.9)
            puestas = int(tramo(t, 0.45, hueco) * (n - desde) + 1e-6)
            return min(n, desde + puestas)
        return min(n, p.get("llenas", 0))

    def _nombre(self, d, caja, p: dict, z, s) -> None:
        nombre = (p.get("nombre") or "").strip()
        tipo = p["tipo"]
        # Las ventanas escriben su nombre en su barra, no en medio del cuerpo.
        if not nombre or tipo in VENTANAS:
            return
        cuerpo = {"chip": 42, "banco": 34, "caja": 40, "disco": 32, "nodo": 26}[tipo]
        ancho = (caja[2] - caja[0]) - 28 * z
        fuente = _ajustar(d, nombre, "grotesca", max(8, round(cuerpo * z)),
                          max(20.0, ancho), max(7, round(13 * z)))
        tw, th, tx, ty = _medir(d, nombre, fuente)
        cx = (caja[0] + caja[2]) / 2 - tw / 2 - tx
        if tipo == "banco":
            d.text((cx, caja[1] + 18 * z - ty), nombre, font=fuente, fill=INK)
        elif tipo in ("disco", "nodo"):
            d.text((cx, caja[3] + 14 * z - ty), nombre, font=fuente, fill=INK)
        else:
            d.text((cx, (caja[1] + caja[3]) / 2 - th / 2 - ty), nombre,
                   font=fuente, fill=INK)

    # ── Las ventanas ──────────────────────────────────────────────────────
    def _tecleado(self, pid: str, n: int, t: float) -> tuple[int, float]:
        """Cuántas líneas se ven ya y cuánto va escrito de la siguiente.

        Sin `teclear` están todas desde el primer fotograma, que es lo que hace
        falta cuando la ventana es el decorado de otra cosa. Con `teclear` la
        ventana **es** la toma: las líneas salen una a una y la que está en
        curso se escribe carácter a carácter, porque ver aparecer el comando es
        la mitad de lo que se está contando.
        """
        a = self.animacion
        if a.get("tipo") != "teclear" or a.get("en") != pid or not n:
            return n, 0.0
        avance = tramo(t, 0.3, max(0.6, self.dur - 0.8)) * n
        return min(n, int(avance)), min(1.0, avance - int(avance))

    def _barra(self, d, caja, p: dict, canto, z) -> float:
        """La barra de la ventana. Devuelve dónde empieza el cuerpo."""
        alto = 56 * z
        d.line([(caja[0], caja[1] + alto), (caja[2], caja[1] + alto)],
               fill=canto, width=max(1, round(2 * z)))
        r = 9 * z
        for k, tinte in enumerate((ALERTA, CALOR, LIMA)):
            cx = caja[0] + (30 + k * 30) * z
            cy = caja[1] + alto / 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      fill=mezcla(PANEL, tinte, 0.55))
        titulo = (p.get("nombre") or "").strip()
        if not titulo:
            return caja[1] + alto
        f = _fuente("mono", max(8, round(26 * z)))
        tw, th, tx, ty = _medir(d, titulo, f)
        if p["tipo"] == "navegador":
            # La dirección va en su píldora, como en un navegador de verdad:
            # es el dato que el espectador tiene que poder leer y reconocer.
            izq, der = caja[0] + 130 * z, caja[2] - 26 * z
            d.rounded_rectangle([izq, caja[1] + 12 * z, der, caja[1] + alto - 12 * z],
                                radius=(alto - 24 * z) / 2,
                                fill=mezcla(PANEL, FONDO, 0.55), outline=FILO,
                                width=max(1, round(2 * z)))
            d.text((izq + 24 * z - tx, caja[1] + alto / 2 - th / 2 - ty), titulo,
                   font=f, fill=APOYO)
        else:
            d.text((caja[0] + (caja[2] - caja[0]) / 2 - tw / 2 - tx,
                    caja[1] + alto / 2 - th / 2 - ty), titulo, font=f, fill=APOYO)
        return caja[1] + alto

    def _ventana(self, d, caja, p: dict, canto, z, t: float) -> None:
        """Un terminal o un navegador, con lo que se lee dentro.

        El navegador **no finge una captura**: dibuja el esqueleto de una
        página —su titular y unas barras de texto—. Fingir el sitio exigiría
        una imagen que nadie ha visto, y un esqueleto dice lo mismo sin
        afirmar nada que no esté en el guion.
        """
        lineas = p.get("lineas") or []
        y = self._barra(d, caja, p, canto, z)
        completas, parcial = self._tecleado(p["id"], len(lineas), t)
        mono = _fuente("mono", max(8, round(27 * z)))
        paso = (48 if p["tipo"] == "terminal" else 46) * z
        y += 24 * z
        for k, linea in enumerate(lineas):
            if k > completas:
                break
            texto = linea if k < completas else linea[:round(len(linea) * parcial)]
            x = caja[0] + 30 * z
            if p["tipo"] == "navegador":
                # La primera línea es el titular de la página; las demás, texto
                # corrido, que se dibuja como lo que es: barras.
                x = self._fila_pagina(d, caja, x, y, texto, k, z)
            else:
                x = self._prompt(d, x, y, texto, mono, z)
            if k == completas and parcial < 1.0:
                self._cursor(d, x, y, mono, z, t)
            y += paso

    def _prompt(self, d, x, y, texto: str, mono, z) -> float:
        """Una línea de terminal. El `$` es del intérprete y va en lima; lo que
        se teclea es del guion y va en tinta; lo que contesta la máquina es
        apoyo. Sin ese contraste las tres cosas parecen la misma."""
        if texto.startswith("$"):
            d.text((x, y), "$", font=mono, fill=LIMA)
            x += _medir(d, "$ ", mono)[0]
            texto = texto[1:].lstrip()
            color = INK
        else:
            color = APOYO
        d.text((x, y), texto, font=mono, fill=color)
        return x + _medir(d, texto, mono)[0]

    def _fila_pagina(self, d, caja, x, y, texto: str, k: int, z) -> float:
        """Devuelve dónde acaba la línea, que es donde va el cursor."""
        if k == 0:
            f = _ajustar(d, texto, "grotesca", max(10, round(40 * z)),
                         max(20.0, caja[2] - caja[0] - 60 * z), max(8, round(18 * z)))
            d.text((x, y), texto, font=f, fill=INK)
            return x + _medir(d, texto, f)[0]
        f = _fuente("mono", max(8, round(24 * z)))
        d.text((x, y), texto, font=f, fill=APOYO)
        ancho = _medir(d, texto, f)[0]
        # Detrás de la línea legible, el resto de la página insinuado: una
        # barra que llega hasta el margen. Es lo que hace que se lea «página».
        if ancho < caja[2] - caja[0] - 120 * z:
            d.rounded_rectangle([x + ancho + 20 * z, y + 8 * z,
                                 caja[2] - 30 * z, y + 24 * z],
                                radius=8 * z, fill=TENUE)
        return x + ancho

    def _cursor(self, d, x, y, mono, z, t: float) -> None:
        ancho, alto = _medir(d, "M", mono)[0], _medir(d, "M", mono)[1]
        if (t % 0.9) < 0.55:
            d.rectangle([x + 4 * z, y, x + 4 * z + ancho, y + alto], fill=LIMA)

    # ── Las animaciones ───────────────────────────────────────────────────
    def _animar(self, d, P, z, s, t: float) -> None:
        a = self.animacion
        tipo = a.get("tipo", "nada")
        if tipo == "flujo":
            self._flujo(d, P, z, a.get("de", ""), a.get("a", ""), t)
        elif tipo == "comparar":
            # Sin ids: corre un flujo por cada vínculo, cada uno a su velocidad.
            # La comparación la hace el ojo, y no hay nada que el modelo pueda
            # equivocar.
            for v in self.vinculos:
                self._flujo(d, P, z, v["de"], v["a"], t)
        elif tipo == "buscar":
            self._buscar(d, P, z, a.get("en", ""), t, 0.0)
        elif tipo == "fallo":
            self._fallo(d, P, z, a.get("en", ""), t)
        elif tipo == "llenar":
            self._llenar(d, P, z, a.get("en", ""), a.get("de", ""), t)
        elif tipo == "espera":
            self._espera(d, P, z, a.get("en", ""), t)

    def _paquete(self, d, P, z, x, y, color=ACENTO, escala=1.0) -> None:
        r = 15 * escala
        caja = _norm([*P(x - r, y - r), *P(x + r, y + r)])
        d.rounded_rectangle(caja, radius=max(1, round(5 * z)), fill=color)

    def _flujo(self, d, P, z, de: str, a: str, t: float, desfase: float = 0.0,
               cuantos: int = 3) -> None:
        ruta = self.ruta(de, a)
        if ruta is None:
            return
        (x0, y0), (x1, y1) = ruta
        cruce = CRUCE_S.get(self.coste(de, a), 1.0)
        lento = cruce >= CRUCE_S["largo"]
        for k in range(cuantos):
            q = ((t - desfase - k * cruce / cuantos) % cruce) / cruce
            if t - desfase - k * cruce / cuantos < 0:
                continue
            # La estela es lo que hace que un cuadrado parezca ir rápido. El
            # que va despacio no la necesita y además se le vería arrastrando.
            for g in range(1 if lento else 4):
                qg = q - g * 0.035
                if qg < 0:
                    continue
                self._paquete(d, P, z, x0 + (x1 - x0) * qg, y0 + (y1 - y0) * qg,
                              mezcla(FONDO, ACENTO, 1.0 - g * 0.22),
                              1.0 - g * 0.12)

    def _barrido(self, d, P, z, pid: str, k: int) -> None:
        rx, ry, rw, rh = self.ranura(pid, k)
        caja = _norm([*P(rx - 8, ry - 6), *P(rx + rw + 8, ry + rh + 6)])
        d.rounded_rectangle(caja, radius=max(1, round(8 * z)), outline=INK,
                            width=max(2, round(4 * z)))

    def _buscar(self, d, P, z, pid: str, t: float, desde: float) -> int:
        """El barrido que recorre las ranuras. Devuelve en cuál va."""
        p = self.piezas.get(pid)
        if p is None or p["tipo"] != "banco" or not p["ranuras"]:
            return -1
        periodo = 1.1
        q = ((t - desde) % periodo) / periodo
        k = min(p["ranuras"] - 1, int(q * p["ranuras"]))
        self._barrido(d, P, z, pid, k)
        return k

    def _fallo(self, d, P, z, pid: str, t: float) -> None:
        """Se busca, no está, y el dato se va a buscar más lejos."""
        p = self.piezas.get(pid)
        if p is None:
            return
        if t < 1.15:
            self._buscar(d, P, z, pid, t, 0.0)
            return
        caja = _norm([*P(p["x"], p["y"]), *P(p["x"] + p["w"], p["y"] + p["h"])])
        if t < 1.75 and (t * 6) % 2 < 1:
            d.rounded_rectangle(caja, radius=max(2, round(18 * z)),
                                outline=ALERTA, width=max(2, round(6 * z)))
        siguiente = next((v["a"] for v in self.vinculos if v["de"] == pid), "")
        if siguiente:
            self._flujo(d, P, z, pid, siguiente, t, desfase=1.8, cuantos=2)

    def _llenar(self, d, P, z, pid: str, de: str, t: float) -> None:
        """Las ranuras se ocupan solas (lo hace `_llenas`); lo que se dibuja
        aquí es de dónde vienen, si vienen de algún sitio."""
        if de and de in self.piezas and pid in self.piezas:
            self._flujo(d, P, z, de, pid, t, cuantos=2)

    def _espera(self, d, P, z, pid: str, t: float) -> None:
        """Lo que hace una pieza mientras otra tarda: nada, y se le ve."""
        p = self.piezas.get(pid)
        if p is None:
            return
        cx, cy = self.centro(pid)
        r = max(p["w"], p["h"]) / 2 + 40
        for k in range(8):
            ang = 2 * math.pi * (k / 8 + (t % 2.4) / 2.4)
            alfa = 0.25 + 0.75 * ((k / 8 + t / 2.4) % 1.0)
            x, y = cx + math.cos(ang) * r, cy + math.sin(ang) * r
            self._paquete(d, P, z, x, y, mezcla(FONDO, APOYO, alfa), 0.42)
        largo = self._vinculo_largo()
        if largo:
            self._flujo(d, P, z, largo["de"], largo["a"], t, cuantos=2)


# ── La cámara ─────────────────────────────────────────────────────────────
# Lo que ocupan arriba los subtítulos y la chapa de contexto. Como el
# titular, están en todas las escenas, así que esto también se reserva siempre.
AIRE_CHAPA = 300
# Y hasta dónde llega un bloque puesto en la banda de arriba, contado desde el
# canto: la banda empieza en 320 y lo más alto que se dibuja ahí mide 360.
AIRE_TARJETA = 680
# El aire que se le deja a la pieza enmarcada contra el canto del cuadro.
AIRE_PIEZA = 40
# Lo que el titular ocupa abajo, y que el esquema no puede invadir **nunca**.
# No es como el aire del bloque, que solo se reserva si el bloque va ahí: el
# titular está en todas las escenas, así que el encuadre vive siempre en los
# dos tercios de arriba. Sin esto, el esquema se mete debajo del texto y lo
# único que lo separa es el plato, que se ve como un parche.
AIRE_TITULAR = 480


def camara(nombre: str, esc: Escenario, p: float, banda: str = "") -> dict:
    """Dónde está la cámara en el instante `p` (de 0 a 1) de la escena.

    Sin rotación a propósito: un esquema torcido se lee peor, y las cajas se
    dibujan alineadas al cuadro. Lo que mueve la escena es lo que pasa dentro,
    no la cámara haciendo filigranas.

    En los planos abiertos la cámara **le deja sitio a la tarjeta**: encuadra
    el esquema en lo que queda de pantalla, no en la pantalla entera. Sin esto,
    el plano general mete la primera pieza justo debajo del rótulo y el plato
    de detrás del texto se la come.
    """
    # La franja en la que cabe el esquema: el cuadro menos lo del titular
    # abajo y, si el bloque va arriba, lo suyo también.
    reserva_arriba = AIRE_TARJETA if banda == "arriba" else AIRE_CHAPA
    aire = reserva_arriba + AIRE_TITULAR
    z = min(ANCHO_LIENZO / esc.ancho,
            (ALTO_LIENZO - aire) / esc.alto) * 0.96
    # El centro de esa franja, no el del cuadro.
    centro = (reserva_arriba + ALTO_LIENZO - AIRE_TITULAR) / 2
    entero = {"x": esc.ancho / 2,
              "y": esc.alto / 2 + (ALTO_LIENZO / 2 - centro) / z,
              "z": z, "rot": 0.0}
    fx, fy = esc.centro(esc.foco)
    # «Cerca» es relativo al encuadre y no un número fijo: en una escena de dos
    # piezas, un zoom absoluto de 1.3 se come el cuadro, y en una de seis no se
    # acerca a nada.
    cerca = z * 1.45
    pieza_foco = esc.piezas.get(esc.foco)
    if pieza_foco is not None:
        # Y acercarse no puede dejar fuera del cuadro aquello a lo que te
        # acercas. Con una ventana pasaba siempre: es ancha y lleva texto
        # dentro, y en una escena de una sola pieza el encuadre entero ya era
        # esa pieza, así que el 1,45 la sacaba del cuadro y el comando se leía
        # a medias.
        cabe = min(ANCHO_LIENZO / (pieza_foco["w"] + 2 * AIRE_PIEZA),
                   (ALTO_LIENZO - aire) / (pieza_foco["h"] + 2 * AIRE_PIEZA))
        cerca = max(z, min(cerca, cabe))
    q = entrada_salida(p)
    if nombre == "entrada":
        return {"x": entero["x"] + (fx - entero["x"]) * q,
                "y": entero["y"] + (fy - entero["y"]) * q,
                "z": z + (cerca - z) * q, "rot": 0.0}
    if nombre == "lateral":
        ancho_visible = ANCHO_LIENZO / cerca
        viaje = min(esc.ancho, ancho_visible) * 0.3
        return {"x": fx - viaje / 2 + viaje * q, "y": fy, "z": cerca, "rot": 0.0}
    if nombre == "cruce":
        return {"x": fx, "y": fy, "z": cerca * (1.0 + 0.08 * q), "rot": 0.0}
    if nombre == "salida":
        sal = salida(p, 2)
        return {"x": fx + (entero["x"] - fx) * sal,
                "y": fy + (entero["y"] - fy) * sal,
                "z": cerca + (z - cerca) * sal, "rot": 0.0}
    return {**entero, "z": z * (1 - 0.05 + 0.05 * q)}
