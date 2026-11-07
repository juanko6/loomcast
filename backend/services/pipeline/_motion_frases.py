"""Cortar la narración por frases y repartirlas en escenas.

El resto de plantillas trocea el audio con una regla de reloj: tantos segundos
por escena y a cortar en el límite de palabra más cercano. Para una imagen por
escena vale, porque la imagen no tiene nada que contar por dentro. Una escena
de motion sí: un dato que cruza un bus, una pila que se llena, una búsqueda que
falla. Eso no dura lo que diga una rejilla, dura lo que dure la idea.

Así que aquí la escena la decide el storyboard, con una condición que no es
negociable: **la voz ya está grabada**. Los cortes tienen que caer donde caen
las palabras o los subtítulos se despegan. Por eso el modelo no dice segundos:
dice cuántas frases van juntas en cada plano, y la duración sale sola de los
tiempos que ya están en `palabras.json`. Una frase corta son dos segundos; tres
frases seguidas, nueve. Y la suma sigue siendo exactamente el audio.
"""
# Por debajo de esto no da tiempo ni a que entre la tarjeta: la escena se funde
# con la siguiente. Por encima del máximo, el plano se parte en dos tomas de la
# misma composición (la segunda continúa) en vez de dejar diez segundos de un
# esquema quieto.
MINIMO_S = 2.2
MAXIMO_S = 11.0
# Una frase de corrido más larga que esto no es una frase, es un párrafo sin
# puntos: se parte por la coma que quede más al medio.
MAX_PALABRAS = 24

_FIN = ".?!…"


def _mayuscula(w: str) -> bool:
    w = w.strip()
    return bool(w) and w[0].isupper()


def frases(palabras: list[dict]) -> list[dict]:
    """Parte las palabras en frases, cada una con sus tiempos exactos.

    Una frase acaba en el punto (o la interrogación) al que le sigue algo que
    empieza en mayúscula. Pedir solo el punto rompe «1.1 kilos» y las siglas;
    pedir solo la mayúscula rompe los nombres propios.
    """
    corte, salida = [], []

    def cerrar():
        if not corte:
            return
        salida.append({
            "texto": " ".join(w["word"].strip() for w in corte).strip(),
            "t_inicio": round(corte[0]["start"], 3),
            "t_fin": round(corte[-1]["end"], 3),
        })
        corte.clear()

    for i, w in enumerate(palabras):
        corte.append(w)
        texto = w["word"].strip()
        siguiente = palabras[i + 1]["word"] if i + 1 < len(palabras) else ""
        if texto and texto[-1] in _FIN and (not siguiente or _mayuscula(siguiente)):
            cerrar()
    cerrar()
    return [f for trozo in salida for f in _partir_larga(trozo, palabras)]


def _partir_larga(frase: dict, palabras: list[dict]) -> list[dict]:
    """Una frase kilométrica se parte por la coma más centrada."""
    ws = frase["texto"].split()
    if len(ws) <= MAX_PALABRAS:
        return [frase]
    comas = [k for k, w in enumerate(ws[:-2]) if w.endswith(",")]
    if not comas:
        return [frase]
    medio = len(ws) / 2
    k = min(comas, key=lambda c: abs(c - medio))
    # El tiempo del corte se busca en las palabras originales: la palabra k de
    # la frase es la que acaba en esa coma.
    dentro = [w for w in palabras
              if frase["t_inicio"] <= w["start"] <= frase["t_fin"]]
    if len(dentro) <= k + 1:
        return [frase]
    t = round(dentro[k]["end"], 3)
    return [
        {"texto": " ".join(ws[:k + 1]), "t_inicio": frase["t_inicio"], "t_fin": t},
        {"texto": " ".join(ws[k + 1:]), "t_inicio": t, "t_fin": frase["t_fin"]},
    ]


def repartir(fs: list[dict], tamanos: list[int]) -> tuple[list[dict], dict]:
    """Agrupa las frases en escenas según lo que pidió el storyboard.

    Del plano se usa **cuántas** frases quería, no cuáles: los índices el
    modelo los baila (se salta una, repite otra, empieza en cero) y entonces
    quedan frases sin escena o escenas sin audio. El tamaño, en cambio, es lo
    que de verdad quiso decir: «esto es una toma» o «esto son tres frases
    juntas». Se reparte en orden y lo que sobre se le da a la última.

    Devuelve un grupo por escena con el plano del que salió, que es lo que deja
    a `escenas.py` emparejar cada escena con lo que el storyboard dijo de ella.
    """
    fallos = {"grupo_corto": 0, "grupo_largo": 0, "planos_sobrantes": 0,
              "frases_sueltas": 0}
    grupos, i = [], 0
    for n, t in enumerate(tamanos):
        if i >= len(fs):
            fallos["planos_sobrantes"] += 1
            continue
        # Lo que queda tiene que alcanzar para los planos que faltan: sin esto,
        # un plano que pide cinco frases deja a los tres siguientes sin nada.
        quedan_planos = len(tamanos) - n - 1
        cabe = max(1, len(fs) - i - quedan_planos)
        cuantas = max(1, min(int(t) if t else 1, cabe))
        grupos.append({"plano": n, "frases": list(range(i, i + cuantas))})
        i += cuantas
    if not grupos:
        grupos = [{"plano": 0, "frases": []}]
    if i < len(fs):
        fallos["frases_sueltas"] += len(fs) - i
        grupos[-1]["frases"] += list(range(i, len(fs)))

    grupos = _fundir_cortos(fs, grupos, fallos)
    # Un grupo sin frases no es una escena: no tiene audio ni duración, y si se
    # colara descuadraría el emparejamiento con los planos.
    return [g for g in _partir_largos(fs, grupos, fallos) if g["frases"]], fallos


def _dur(fs: list[dict], g: dict) -> float:
    if not g["frases"]:
        return 0.0
    return fs[g["frases"][-1]]["t_fin"] - fs[g["frases"][0]]["t_inicio"]


def _fundir_cortos(fs, grupos: list[dict], fallos: dict) -> list[dict]:
    """Una escena de segundo y medio no da tiempo a nada: se pega a su vecina."""
    salida = []
    for g in grupos:
        if salida and _dur(fs, g) < MINIMO_S:
            fallos["grupo_corto"] += 1
            salida[-1]["frases"] += g["frases"]
        else:
            salida.append(g)
    # Si la primera es la corta, no hay anterior a la que pegarla: va con la
    # siguiente, y el plano que manda es el suyo, que es el que establece.
    while len(salida) > 1 and _dur(fs, salida[0]) < MINIMO_S:
        fallos["grupo_corto"] += 1
        salida[0]["frases"] += salida[1]["frases"]
        del salida[1]
    return salida


def _partir_largos(fs, grupos: list[dict], fallos: dict) -> list[dict]:
    """Un plano que se come medio vídeo se parte en tomas de la misma
    composición: la segunda continúa, así que no se rehace el esquema, solo
    cambia la cámara."""
    salida = []
    for g in grupos:
        dur = _dur(fs, g)
        if dur <= MAXIMO_S or len(g["frases"]) < 2:
            salida.append(g)
            continue
        fallos["grupo_largo"] += 1
        trozos = min(len(g["frases"]), int(dur // MAXIMO_S) + 1)
        tam = len(g["frases"]) / trozos
        for k in range(trozos):
            cacho = g["frases"][round(k * tam):round((k + 1) * tam)]
            if cacho:
                salida.append({"plano": g["plano"], "frases": cacho,
                               "sigue": k > 0})
    return salida


def _reloj(trozos: list[dict], t_inicio: float, t_fin: float) -> list[dict]:
    """Cuándo entra y cuándo sale el titular de cada frase de la escena.

    El clip de una escena empieza su reloj en cero, así que lo que
    `palabras.json` da en absoluto hay que traerlo a esa referencia. Y por lo
    mismo que las escenas se pegan unas a otras, el titular de una frase dura
    hasta que **empieza** la siguiente: si durase solo lo que suena la frase,
    cada silencio dejaría la pantalla sin texto y el vídeo parpadearía.
    """
    reloj = []
    for k, f in enumerate(trozos):
        releva = trozos[k + 1]["t_inicio"] if k + 1 < len(trozos) else t_fin
        reloj.append({
            "texto": f["texto"],
            "t0": round(max(0.0, f["t_inicio"] - t_inicio), 3),
            "t1": round(max(0.0, releva - t_inicio), 3),
        })
    return reloj


def segmentos(fs: list[dict], grupos: list[dict], fin_audio: float) -> list[dict]:
    """De grupos de frases a lo que el resto del pipeline llama segmento.

    **Las escenas se pegan unas a otras.** Una frase empieza cuando empieza su
    primera palabra y acaba con la última, así que entre dos frases hay un
    silencio que no es de ninguna. Si cada escena durase solo sus frases, los
    clips sumarían menos que la voz —cinco segundos menos en el primer vídeo de
    prueba— y como el montaje los encadena, cada escena entraría antes que lo
    que se está diciendo: el vídeo se despega del audio y va a peor.

    Así que el corte de una escena es **el comienzo de la siguiente**, el
    silencio se lo queda la que viene antes, y la última llega hasta el final
    del audio. La suma vuelve a ser exactamente la voz.
    """
    salida = []
    for n, g in enumerate(grupos):
        trozos = [fs[i] for i in g["frases"]]
        if not trozos:
            continue
        siguiente = next((grupos[k] for k in range(n + 1, len(grupos))
                          if grupos[k]["frases"]), None)
        t_inicio = salida[-1]["t_fin"] if salida else 0.0
        t_fin = (fs[siguiente["frases"][0]]["t_inicio"] if siguiente
                 else round(max(fin_audio, trozos[-1]["t_fin"]), 3))
        salida.append({
            "t_inicio": t_inicio,
            "t_fin": t_fin,
            "texto": " ".join(t["texto"] for t in trozos),
            "frases": _reloj(trozos, t_inicio, t_fin),
        })
    return salida


def numeradas(fs: list[dict]) -> str:
    """Las frases como se las lee el storyboard, con lo que dura cada una."""
    return "\n".join(
        f"{i + 1}. [{f['t_fin'] - f['t_inicio']:.1f}s] {f['texto']}"
        for i, f in enumerate(fs)
    )
