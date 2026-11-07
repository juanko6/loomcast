"""Revisar y reparar lo que el LLM escribe para una escena de motion.

El modelo acierta mucho y falla siempre un poco, y aquí los fallos no son
estéticos: una tarjeta con dos palabras de más no se lee en un móvil, una
cifra que no está en el guion es una mentira publicada con tu cara, y dos
escenas seguidas con el mismo bloque hacen que el vídeo parezca congelado. Así
que nada se da por bueno: todo se comprueba y se arregla, y se cuenta cuántas
veces hizo falta.

**El orden importa, y costó verlo.** Hay dos revisiones y la primera va antes
de pedir ningún texto. El bloque decide qué clase de texto se escribe —un
titular es una frase y una píldora es el nombre de una cosa—, así que si la
variedad se arregla después, cuando el texto ya existe, acaba metiéndose una
frase entera dentro de una etiqueta de tres palabras. Se repara el plano
primero (`revisar_planos`) y cada ficha se escribe ya sabiendo en qué bloque
va; luego se revisa la ficha (`revisar_fichas`).
"""
import re

from ._motion_escena import (ANIMACIONES, COSTES, ESTADOS, FONDOS,
                             MAX_COLUMNAS, MAX_LINEAS, MAX_PIEZAS, MAX_RANURAS,
                             TIPOS, VENTANAS)

BLOQUES = ("NADA", "ROTULO", "CIFRA", "PILDORA", "CIRCULO", "GRAFICA",
           "LISTA", "ORDINAL")
BANDAS = ("arriba", "centro")
CAMARAS = ("general", "entrada", "lateral", "cruce", "salida")

# A cuáles se rota cuando el storyboard repite un bloque. `NADA` va el primero
# a propósito: desde que el titular se releva con la voz, la pantalla ya no se
# congela por no poner nada encima, y la toma sin bloque es la más común del
# lenguaje que se está copiando. El rótulo y la cifra quedan fuera: el primero
# establece una vez y la segunda necesita un número del guion.
ROTACION = ("NADA", "CIRCULO", "PILDORA", "LISTA", "GRAFICA")
# Los que pueden repetirse sin que el vídeo parezca atascado: el que no dibuja
# nada, y el ordinal, que precisamente cuenta por dónde vamos.
REPETIBLES = ("NADA", "ORDINAL")
# Dónde va cada bloque si el modelo no elige banda, o elige la ya ocupada.
BANDA_NATURAL = {"NADA": "centro", "ROTULO": "arriba", "CIFRA": "arriba",
                 "PILDORA": "centro", "CIRCULO": "arriba", "GRAFICA": "centro",
                 "LISTA": "centro", "ORDINAL": "arriba"}
# Palabras de `texto` y de `apoyo` que caben en cada bloque. En LISTA el texto
# no se dibuja —lo que se ve son las filas— y en NADA no hay nada que medir.
TOPE = {"NADA": (0, 0), "ROTULO": (4, 2), "CIFRA": (1, 4), "PILDORA": (5, 0),
        "CIRCULO": (8, 5), "GRAFICA": (6, 4), "LISTA": (0, 0), "ORDINAL": (1, 0)}
# El titular de una frase: hasta siete palabras, y una sola en el acento.
TOPE_TITULAR = 7
# Lo que cabe en la chapa de contexto sin dejar de leerse de un vistazo.
TOPE_CHAPA = 4
MAX_FILAS = 5

# Cortar a N palabras a ciegas deja la tarjeta colgando ("un fantasma digital
# en"), que en pantalla es peor que una tarjeta larga. Mismo recurso que
# `escenas._breve` con las fichas del reparto.
_ENLACE = {"de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas",
           "en", "con", "por", "para", "y", "o", "a", "al", "que", "su", "sus",
           "lo", "se", "desde", "hasta", "sobre", "entre", "sin", "como"}


def _palabras(s: str) -> list[str]:
    return [w for w in re.split(r"\s+", (s or "").strip()) if w]


def cortar(s: str, n: int) -> str:
    """Corta a n palabras y suelta los enlaces que queden al final."""
    if not n:
        return ""
    ws = _palabras(s)[:n]
    while ws and ws[-1].lower().strip(" .,;:") in _ENLACE:
        ws.pop()
    return " ".join(ws)


def revisar_planos(planos, n: int, hay_cifras: bool) -> tuple[list[dict], dict]:
    """Arregla el storyboard antes de que se escriba una sola tarjeta.

    `accion` llega como "BLOQUE: lo que señala este plano". De ahí sale el
    bloque, y lo que venga detrás se le pasa tal cual al que escribe la ficha.
    """
    fallos = {"bloque": 0, "bloque_repetido": 0, "camara": 0, "cifra_sin_numeros": 0}
    salida, ultimos, usados = [], [], set()
    for i, pl in enumerate(planos):
        accion = (pl.accion or "").strip()
        cabeza, _, resto = accion.partition(":")
        bloque = cabeza.strip().upper()
        if bloque not in BLOQUES:
            fallos["bloque"] += 1
            bloque, resto = ROTACION[i % len(ROTACION)], accion
        # Una CIFRA en un guion sin números solo puede acabar en un número
        # inventado. Se corta aquí, antes de pedírselo a nadie.
        if bloque == "CIFRA" and not hay_cifras:
            fallos["cifra_sin_numeros"] += 1
            bloque = "NADA"
        # El storyboard tiene prohibido repetir bloque dos planos seguidos y lo
        # incumple igual. Se rota entre los que caben, no se cambia siempre al
        # mismo: eso solo cambia una monotonía por otra y deja el vídeo haciendo
        # pimpón entre dos bloques. Se miran los **dos** planos anteriores y no
        # solo el último, porque A-B-A-B cumple la regla de no repetir seguido
        # y en pantalla se ve igual de congelado que A-A-A.
        if bloque in ultimos and bloque not in REPETIBLES:
            fallos["bloque_repetido"] += 1
            for cand in ROTACION:
                if cand in ultimos:
                    continue
                # La gráfica y la lista son remates: una sola de cada, y en
                # el último tercio. Una lista en el primer plano enumera algo
                # que todavía no se ha contado.
                if cand in ("GRAFICA", "LISTA") and (
                        cand in usados or i < n * 2 // 3):
                    continue
                bloque = cand
                break
        usados.add(bloque)
        ultimos = (ultimos + [bloque])[-2:]

        camara = (pl.camara or "").strip().lower()
        if camara not in CAMARAS:
            fallos["camara"] += 1
            camara = CAMARAS[i % len(CAMARAS)]
        # Lo que se señala hay que verlo: de lejos no hay nada que señalar.
        if bloque in ("CIRCULO", "PILDORA") and camara == "general":
            camara = "entrada"
        salida.append({"bloque": bloque, "camara": camara,
                       "chapa": cortar(pl.chapa, TOPE_CHAPA).strip(" ."),
                       "accion": f"{bloque}: {resto.strip() or accion}"})
    return salida, fallos


def _titulares(crudos, frases: list[dict], fallos: dict) -> list[dict]:
    """Un titular por frase de la escena, con los tiempos de la voz puestos.

    Los tiempos no se le piden al modelo nunca: los tiene el audio. Los
    índices tampoco, porque los baila (ver `_motion_frases.repartir`). Lo
    único que se comprueba es que haya tantos titulares como frases: si
    sobran, se tiran los últimos; si faltan, esa frase se queda con un recorte
    de sí misma, que se lee peor pero entra y sale cuando tiene que hacerlo.
    """
    salida = []
    for k, fr in enumerate(frases):
        crudo = crudos[k] if k < len(crudos) else None
        texto = cortar(getattr(crudo, "texto", "") or "", TOPE_TITULAR).strip(" .")
        if not texto:
            fallos["titular_vacio"] += 1
            texto = cortar(fr["texto"], 6).strip(" .")
        bajas = [w.lower().strip(" .,") for w in _palabras(texto)]
        pedido = [e for e in (getattr(crudo, "enfasis", None) or [])][:1]
        enfasis = [e for e in pedido if e.lower().strip(" .,") in bajas]
        if len(enfasis) != len(pedido):
            fallos["enfasis_fuera"] += 1
        salida.append({"texto": texto, "enfasis": enfasis,
                       "t0": fr["t0"], "t1": fr["t1"]})
    if len(crudos) > len(frases):
        fallos["titulares_de_mas"] += 1
    return salida


def _filas(crudas, fallos: dict) -> list[dict]:
    """Las filas de una LISTA, recortadas a lo que cabe en una fila."""
    crudas = list(crudas or [])
    if len(crudas) > MAX_FILAS:
        fallos["filas_de_mas"] += 1
    filas = []
    for fl in crudas[:MAX_FILAS]:
        texto = cortar(getattr(fl, "texto", "") or "", 5).strip(" .")
        if texto:
            filas.append({
                "texto": texto,
                "chapa": cortar(getattr(fl, "chapa", "") or "", 3).strip(" ."),
            })
    return filas


def revisar_fichas(fichas, planos: list[dict], segmentos: list[dict],
                   guion_txt: str) -> tuple[list[dict], dict]:
    """Valida cada ficha contra su plano ya revisado y la repara."""
    fallos = {"no_hizo_caso": 0, "banda": 0, "banda_repetida": 0, "largas": 0,
              "cifra_inventada": 0, "enfasis_fuera": 0, "vacia": 0,
              "titular_vacio": 0, "titulares_de_mas": 0, "filas_de_mas": 0,
              "bloque_sin_datos": 0}
    cifras = set(re.findall(r"\d[\d.,]*", guion_txt))
    salida, banda_previa = [], ""

    for i, f in enumerate(fichas):
        # El bloque ya está decidido: la ficha solo puede confirmarlo.
        bloque = planos[i]["bloque"]
        if (f.bloque or "").strip().upper() != bloque:
            fallos["no_hizo_caso"] += 1

        titulares = _titulares(list(f.titulares or []),
                               segmentos[i].get("frases") or [], fallos)
        filas = _filas(f.filas, fallos) if bloque == "LISTA" else []

        texto = cortar(f.texto, TOPE[bloque][0] + 4).strip(" .")
        apoyo = cortar(f.apoyo, TOPE[bloque][1] + 2).strip(" .")
        if bloque not in ("NADA", "LISTA") and not texto:
            fallos["vacia"] += 1
            texto = cortar(segmentos[i]["texto"], 6)

        # Un bloque al que le faltan sus datos no se dibuja a medias: se
        # apaga. Una lista de una fila no es una lista, y un ordinal sin
        # número no es nada. Apagarlo deja la toma en esquema y titular, que
        # es una toma correcta, y no una caja vacía en mitad de la pantalla.
        if bloque == "LISTA" and len(filas) < 2:
            fallos["bloque_sin_datos"] += 1
            bloque = "NADA"
        if bloque == "ORDINAL" and not re.search(r"\d", texto):
            fallos["bloque_sin_datos"] += 1
            bloque = "NADA"

        # Una cifra cuyo número no está en el guion es exactamente la mentira
        # que este formato invita a contar. Se apaga el bloque: el dato lo
        # cuenta la voz, y el titular de esa frase ya lo lleva escrito.
        if bloque == "CIFRA":
            n = re.search(r"\d[\d.,]*", texto)
            if not n or n.group(0) not in cifras:
                fallos["cifra_inventada"] += 1
                bloque, texto, apoyo = "NADA", "", ""

        if len(_palabras(texto)) > TOPE[bloque][0]:
            fallos["largas"] += 1
            texto = cortar(texto, TOPE[bloque][0])
        apoyo = cortar(apoyo, TOPE[bloque][1])

        banda = (f.banda or "").strip().lower()
        if bloque == "NADA":
            # Sin bloque no hay banda que ocupar, y tampoco que reservar: la
            # escena siguiente puede usar la que quiera.
            banda, banda_previa = "centro", ""
        else:
            if banda not in BANDAS:
                fallos["banda"] += 1
                banda = BANDA_NATURAL[bloque]
            if banda == banda_previa:
                fallos["banda_repetida"] += 1
                banda = next(b for b in BANDAS if b != banda_previa)
            banda_previa = banda

        bajas = [w.lower().strip(" .,") for w in _palabras(texto)]
        enfasis = [e for e in f.enfasis if e.lower().strip(" .,") in bajas][:2]
        if len(enfasis) != len(list(f.enfasis)[:2]):
            fallos["enfasis_fuera"] += 1
        # En estos dos el bloque entero ya es el acento.
        if bloque in ("CIFRA", "PILDORA"):
            enfasis = []

        salida.append({"bloque": bloque, "banda": banda, "texto": texto,
                       "apoyo": apoyo, "enfasis": enfasis, "filas": filas,
                       "titulares": titulares, "chapa": planos[i]["chapa"],
                       "camara": planos[i]["camara"]})
    return salida, fallos


# ── El dibujo ─────────────────────────────────────────────────────────────
# Qué animación necesita qué. `banco` quiere decir que el objetivo tiene que
# ser una pila de ranuras: barrer un chip no se ve.
_NECESITA_BANCO = ("buscar", "fallo", "llenar")
_NECESITA_RUTA = ("flujo",)
_NECESITA_PIEZA = ("latido", "espera")
# Teclear solo se ve dentro de una ventana: en un chip no hay cursor.
_NECESITA_VENTANA = ("teclear",)
# Qué campos usa cada animación. Lo que no esté aquí se vacía al revisar.
_CAMPOS = {"flujo": ("de", "a"), "buscar": ("en",), "fallo": ("en",),
           "llenar": ("en", "de"), "latido": ("en",), "espera": ("en",),
           "comparar": (), "teclear": ("en",), "nada": ()}

FALLOS_DIBUJO = ("pieza_tipo", "pieza_estado", "pieza_sin_id", "piezas_de_mas",
                 "vinculo_roto", "abanico", "animacion", "foco", "fondo",
                 "sin_piezas", "ventana_vacia")


def _id_libre(usados: set, n: int) -> str:
    base = f"p{n}"
    while base in usados:
        n += 1
        base = f"p{n}"
    return base


def _piezas(crudas, fallos: dict) -> list[dict]:
    """Deja las piezas con un tipo, un id único y unas ranuras que existen."""
    salida, vistos = [], set()
    for p in crudas:
        # Los bloques de anotación los dibuja el renderizador encima; no son
        # cosas del esquema. El modelo lo confunde y declara una pieza llamada
        # «grafica» para la gráfica, que sale como una caja vacía al lado.
        if (p.id or "").strip().upper() in BLOQUES or \
                (p.nombre or "").strip().upper() in BLOQUES:
            fallos["pieza_tipo"] += 1
            continue
        pid = (getattr(p, "id", "") or "").strip().lower().replace(" ", "_")[:24]
        if not pid or pid in vistos:
            fallos["pieza_sin_id"] += 1
            pid = _id_libre(vistos, len(salida) + 1)
        vistos.add(pid)

        tipo = (p.tipo or "").strip().lower()
        if tipo not in TIPOS:
            fallos["pieza_tipo"] += 1
            tipo = "caja"
        estado = (p.estado or "").strip().lower()
        if estado not in ESTADOS:
            fallos["pieza_estado"] += 1
            estado = "normal"
        # Las ranuras solo significan algo en un banco: en un chip son una caja
        # con rayas dentro y el nombre ya no cabe.
        ranuras = max(2, min(MAX_RANURAS, p.ranuras or 4)) if tipo == "banco" else 0
        # Las líneas solo significan algo dentro de una ventana. En una caja
        # no hay dónde escribirlas, y dejarlas ahí solo sirve para que el
        # modelo crea que cualquier pieza puede llevar texto dentro.
        lineas = []
        if tipo in VENTANAS:
            lineas = []
            for cruda in (p.lineas or []):
                # Lo largo se parte, no se recorta: un comando cortado por la
                # mitad es peor que no enseñarlo. La continuación va sangrada,
                # como la escribiría un terminal de verdad.
                cruda = (cruda or "").strip()
                while cruda and len(lineas) < MAX_LINEAS:
                    lineas.append(cruda[:MAX_COLUMNAS])
                    cruda = ("  " + cruda[MAX_COLUMNAS:]) if \
                        len(cruda) > MAX_COLUMNAS else ""
            if not lineas:
                fallos["ventana_vacia"] += 1
                tipo = "caja"
        salida.append({
            "id": pid, "tipo": tipo, "nombre": cortar(p.nombre, 3),
            "ranuras": ranuras, "llenas": max(0, min(ranuras, p.llenas or 0)),
            "estado": estado, "lineas": lineas,
        })
    if len(salida) > MAX_PIEZAS:
        # Seis cajas ya llenan un vertical. A la séptima, o no se lee el
        # nombre o no se ve de qué va la escena.
        fallos["piezas_de_mas"] += len(salida) - MAX_PIEZAS
        salida = salida[:MAX_PIEZAS]
    return salida


def _heredar(piezas: list[dict], previa: dict) -> list[dict]:
    """Las piezas de la escena anterior, con lo que esta cambie encima.

    Es lo que hace que el esquema se monte en vez de rehacerse: la escena 5
    solo dice «aparece la L2 y la L1 se pone caliente», y lo demás sigue donde
    estaba. Si rehiciera la lista entera, el dibujo pegaría un salto en cada
    corte aunque las piezas fueran las mismas.
    """
    fusion = {p["id"]: dict(p) for p in (previa.get("piezas") or [])}
    for p in piezas:
        if p["id"] in fusion:
            # Del que ya estaba solo cambia lo que puede cambiar: cómo está y
            # cuánto lleva dentro. El nombre y el tipo son su identidad.
            cambia = {"estado": p["estado"], "llenas": p["llenas"]}
            # Las líneas de una ventana sí son algo que cambia: el plano
            # siguiente es el comando siguiente. El nombre y el tipo no.
            if p["lineas"]:
                cambia["lineas"] = p["lineas"]
            fusion[p["id"]].update(cambia)
        else:
            fusion[p["id"]] = p
    return list(fusion.values())


def _vinculos(crudos, ids: set, fallos: dict) -> list[dict]:
    salida, vistos = [], set()
    for v in crudos:
        de = (getattr(v, "de", "") or "").strip().lower()
        a = (getattr(v, "a", "") or "").strip().lower()
        if de not in ids or a not in ids or de == a or (de, a) in vistos:
            fallos["vinculo_roto"] += 1
            continue
        vistos.add((de, a))
        coste = (v.coste or "").strip().lower()
        salida.append({"de": de, "a": a,
                       "coste": coste if coste in COSTES else "medio"})
    return salida


_ORDEN_COSTE = {"corto": 0, "medio": 1, "largo": 2}


def _encadenar(vinculos: list[dict], fallos: dict) -> list[dict]:
    """Un abanico de costes distintos desde la misma pieza es una jerarquía.

    El modelo escribe `cpu→l1 corto`, `cpu→l2 medio`, `cpu→ram largo`: visto de
    cerca no está mal, porque el procesador habla con las tres. Pero lo que se
    dibuja entonces es una fila con las tres al mismo lado, y lo que el vídeo
    quería contar —que una está al lado y la otra lejísimos— desaparece. Se le
    pide la cadena en el prompt y lo sigue haciendo, así que se endereza aquí:
    se ordenan por coste y se encadenan, que es el dibujo que explica.

    Solo cuando salen tres o más de la misma pieza **y** con costes
    distintos. Dos salidas, o tres al mismo coste, son alternativas de verdad y
    se quedan como están.
    """
    por_origen = {}
    for v in vinculos:
        por_origen.setdefault(v["de"], []).append(v)
    salida = list(vinculos)
    for de, vs in por_origen.items():
        if len(vs) < 3 or len({v["coste"] for v in vs}) < 2:
            continue
        fallos["abanico"] += 1
        cadena = sorted(vs, key=lambda v: _ORDEN_COSTE.get(v["coste"], 1))
        for v in vs:
            salida.remove(v)
        anterior = de
        for v in cadena:
            salida.append({"de": anterior, "a": v["a"], "coste": v["coste"]})
            anterior = v["a"]
    return salida


def _animacion(cruda, piezas: list[dict], vinculos: list[dict],
               fallos: dict) -> dict:
    """La animación, comprobada contra lo que hay dibujado de verdad.

    Una animación que señala a una pieza que no existe no es un detalle: es un
    clip en el que no se mueve nada y nadie se entera de por qué.
    """
    por_id = {p["id"]: p for p in piezas}
    bancos = [p["id"] for p in piezas if p["tipo"] == "banco"]
    ventanas = [p["id"] for p in piezas if p["tipo"] in VENTANAS]
    tipo = (getattr(cruda, "tipo", "") or "").strip().lower()
    de = (getattr(cruda, "de", "") or "").strip().lower()
    a = (getattr(cruda, "a", "") or "").strip().lower()
    en = (getattr(cruda, "en", "") or "").strip().lower()
    malo = tipo not in ANIMACIONES

    if tipo in _NECESITA_RUTA and not (de in por_id and a in por_id):
        # Quería mover algo entre dos sitios y se equivocó de nombre: se usa el
        # primer vínculo, que es por donde iba a ir de todos modos.
        malo = True
        if vinculos:
            de, a = vinculos[0]["de"], vinculos[0]["a"]
        else:
            tipo = "latido"
    if tipo in _NECESITA_BANCO and en not in bancos:
        malo = True
        if bancos:
            en = bancos[0]
        else:
            tipo = "latido"
    if tipo in _NECESITA_VENTANA and en not in ventanas:
        malo = True
        if ventanas:
            en = ventanas[0]
        else:
            tipo = "latido"
    if tipo in _NECESITA_PIEZA and en not in por_id:
        malo = True
        en = piezas[-1]["id"] if piezas else ""
    if tipo == "comparar" and len(vinculos) < 2:
        # Comparar es poner dos caminos a la vez: con uno solo no hay nada que
        # comparar y se queda en el flujo que sí existe.
        malo = True
        tipo, (de, a) = ("flujo", (vinculos[0]["de"], vinculos[0]["a"])) if vinculos \
            else ("nada", ("", ""))
    if tipo == "nada" and ventanas:
        # Una ventana quieta es una captura. Lo que se está contando es que
        # alguien escribe ahí dentro, así que si no se pidió otra cosa, se
        # teclea.
        malo, tipo, en = True, "teclear", ventanas[0]
    if tipo == "nada" and vinculos and len(piezas) > 1:
        # Un esquema quieto durante ocho segundos es una diapositiva, y una
        # escena de motion que no se mueve no explica nada que no dijera ya el
        # subtítulo. Si hay por dónde, algo tiene que circular.
        malo = True
        tipo = "comparar" if len(vinculos) > 1 else "flujo"
        de, a = vinculos[0]["de"], vinculos[0]["a"]
    if not piezas:
        tipo, malo = "nada", malo or tipo != "nada"
    if tipo not in ANIMACIONES:
        tipo = "nada"
    if malo:
        fallos["animacion"] += 1
    # Los campos que esta animación no usa se vacían, y los que usa tienen que
    # ser piezas de verdad. Si se quedan, el `foco` acaba apuntando a un id que
    # el modelo escribió para otra cosa y la cámara enmarca la nada.
    usa = _CAMPOS.get(tipo, ())
    return {"tipo": tipo,
            **{campo: (valor if campo in usa and valor in por_id else "")
               for campo, valor in (("de", de), ("a", a), ("en", en))}}


def revisar_dibujo(comp, plano: dict, previa: dict | None) -> tuple[dict, dict]:
    """Lo que se dibuja en una escena, ya comprobado contra sí mismo.

    Se revisa **después** de heredar, no antes: una escena que continúa puede
    animar una pieza que no declaró porque ya estaba en pantalla, y si se
    comprobara contra su propia lista se le borraría la animación por señalar
    a algo que para ella no existe.
    """
    fallos = {k: 0 for k in FALLOS_DIBUJO}
    piezas = _piezas(comp.piezas, fallos)
    if plano.get("continua") and previa:
        piezas = _heredar(piezas, previa)[:MAX_PIEZAS]
    if not piezas:
        fallos["sin_piezas"] += 1

    ids = {p["id"] for p in piezas}
    vinculos = _vinculos(comp.vinculos, ids, fallos)
    if plano.get("continua") and previa:
        viejos = [v for v in previa.get("vinculos", [])
                  if v["de"] in ids and v["a"] in ids
                  and not any(w["de"] == v["de"] and w["a"] == v["a"]
                              for w in vinculos)]
        vinculos = viejos + vinculos
    vinculos = _encadenar(vinculos, fallos)

    animacion = _animacion(comp.animacion, piezas, vinculos, fallos)
    foco = (comp.foco or "").strip().lower()
    if foco not in ids:
        if foco:
            fallos["foco"] += 1
        foco = animacion.get("en") or animacion.get("a") or (
            piezas[-1]["id"] if piezas else "")
    fondo = (comp.fondo or "").strip().lower()
    if fondo not in FONDOS:
        fallos["fondo"] += 1
        fondo = "negro"
    return {"fondo": fondo, "piezas": piezas, "vinculos": vinculos,
            "animacion": animacion, "foco": foco}, fallos
