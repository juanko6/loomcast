"""Etapa 6 — ESCENAS: segmentar la narración y generar prompts visuales.

Divide el audio en intervalos de ~duracion_escena_s (cortando en límites de
palabra según palabras.json) y pide al LLM dos prompts en inglés por escena —
el visual (para la imagen) y el de movimiento (para el modo i2v) —, con el
guion completo como contexto y el estilo de la plantilla.

Antes de eso, una sola llamada hace el storyboard: el mundo visual del video y
un plano por segmento (cámara + qué pasa). Cada prompt de escena se escribe
por separado y sin memoria de los demás, así que sin un plan común todos caen en
el mismo retrato del protagonista desde otro ángulo — con un objeto, un pase de
diapositivas de producto en vez de algo que ocurre. El storyboard decide la
secuencia de una vez y cada escena recibe su plano junto al anterior y al
siguiente.

Las plantillas de montaje **motion** van por otro camino (`_generar_motion`) y
cambian dos cosas de raíz. La primera es el corte: la narración se parte en
frases y es el storyboard el que decide cuántas van en cada toma, así que las
escenas duran lo que dura su idea en vez de lo que diga una rejilla (ver
`_motion_frases`). La segunda es lo que devuelve cada escena: no dos prompts en
inglés para un generador de imágenes, sino su **composición** —las piezas que
se dibujan, qué conecta con qué, qué se anima y la tarjeta que se lee encima—,
y una escena puede heredar el dibujo de la anterior en vez de empezar de cero.
Lo que el modelo escribe se revisa y se repara antes de guardarlo
(`_motion_ficha`), porque aquí un fallo no es un prompt flojo: es una tarjeta
que no se lee, una cifra que el guion no dice o una animación que señala a una
pieza que no existe y deja el clip quieto.

Si el proyecto tiene reparto (ver casting.py), al LLM se le pide que referencie
a cada personaje con su marcador {CLAVE} en vez de describirlo, y aquí se
sustituye por su ficha literal. Así el mismo personaje llega al generador con
exactamente las mismas palabras en todas sus escenas.
"""
import json
import math
import random
import re

from ...clients import llm
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import guiones as guiones_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import personajes as personajes_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...schemas import (ComposicionLLM, EscenaLLM, PlanoLLM, StoryboardLLM,
                        StoryboardMotionLLM)
from ... import parada
from .. import progreso
from . import _motion_ficha, _motion_frases

# Cierre de cada mensaje. Un servidor que no aplica el json_schema (mlx_lm)
# deja al modelo libre, y si lo último que lee es un plano que empieza por
# "{SHAKY}’s sensor head…", toma la llave por el principio del marcador y
# escribe el prompt suelto en vez del JSON. Recordarle al final con qué tiene
# que empezar lo evita; un "responde en JSON" a secas no bastó.
def _solo_json(primera_clave: str) -> str:
    return ("\n\nAnswer with the JSON object only, as the system prompt "
            f'specifies, starting with {{"{primera_clave}":')

# Cualquier marcador que sobreviva a la sustitución: o el LLM se inventó una
# clave que no existe, o escribió llaves por su cuenta.
_MARCADOR = re.compile(r"\{([^{}]*)\}")


def _segmentar(palabras: list[dict], duracion_escena_s: float) -> list[dict]:
    """Reparte las palabras en N intervalos de duración similar."""
    fin_audio = palabras[-1]["end"]
    n = max(1, math.ceil(fin_audio / duracion_escena_s))
    limites = [fin_audio * i / n for i in range(n + 1)]
    segmentos = []
    for i in range(n):
        del_intervalo = [
            w for w in palabras if limites[i] <= w["start"] < limites[i + 1]
        ]
        if not del_intervalo:
            continue
        segmentos.append({
            "t_inicio": round(limites[i], 3),
            "t_fin": round(limites[i + 1], 3),
            "texto": " ".join(w["word"].strip() for w in del_intervalo),
        })
    # El último segmento cubre hasta el final real del audio
    if segmentos:
        segmentos[-1]["t_fin"] = round(fin_audio, 3)
    return segmentos


_ENLACE = {"a", "an", "the", "of", "from", "in", "on", "at", "to", "with",
           "and", "or", "for", "by", "her", "his", "their", "its"}


def _breve(ficha: str) -> str:
    """Identificación corta del personaje: lo que va antes del primer detalle.

    "a woman in her early thirties with dark curls, warm brown eyes, …" →
    "a woman in her early thirties". Sirve para el prompt de movimiento, que
    debe caber en 25-45 palabras y solo necesita saber quién se mueve, no cómo
    es de la cabeza a los pies.
    """
    cabeza = re.split(r"[,;]| with | wearing ", ficha, maxsplit=1)[0].strip()
    palabras = cabeza.split()
    if len(palabras) > 8:
        # Cortar a 8 a ciegas deja la frase colgando ("a camera from the
        # late"): se corta antes del primer complemento.
        palabras = palabras[:8]
        enlace = next((i for i, w in enumerate(palabras) if i >= 2 and w.lower() in _ENLACE), None)
        palabras = palabras[:enlace]
    return " ".join(palabras) if palabras else ficha


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[\w'’-]+", texto.lower())


def _quitar_eco(prompt: str, marca: str, ficha: str) -> str:
    """Quita la descripción que el LLM pega junto al marcador.

    Aunque se le pide que no lo haga, el modelo tiende a escribir "{SHAKY}, a
    vintage robot with a boxy chassis, standing…" o "a vintage robot {SHAKY}":
    al sustituir, la ficha sale dos veces, el prompt se va en describir al
    personaje y la imagen acaba siendo su retrato. Se quita lo que va pegado al
    marcador si casi todas sus palabras ya están en la ficha; lo que añade algo
    (acción, lugar, encuadre) no pasa ese filtro y se queda.
    """
    vocab = set(_palabras(ficha))

    def eco(trozo: str) -> bool:
        ws = _palabras(trozo)
        return bool(ws) and sum(w in vocab for w in ws) / len(ws) >= 0.7

    partes = prompt.split(marca)
    for k in range(len(partes) - 1):
        # Delante: "…of a vintage robot {X}" (o "…of a robot, {X}") → "…of {X}".
        # Se prueba desde el
        # artículo más cercano hacia atrás y se queda el tramo más largo. Un
        # artículo solo ("the {X}") sobra siempre: la ficha ya trae el suyo.
        antes, corte = partes[k], None
        for m in reversed(list(re.finditer(r"\b(?:an?|the)\s+", antes, re.I))):
            tramo = antes[m.end():]
            if not re.fullmatch(r"(?:[\w'’-]+,?\s+){0,10}", tramo):
                break
            if not tramo or eco(tramo):
                corte = m.start()
        if corte is not None:
            partes[k] = antes[:corte]
        # Detrás: "{X}, a vintage robot with…, visible wiring, standing" →
        # "{X}, standing". Arranca solo con una aposición ("a …"/"an …").
        despues = partes[k + 1]
        m = re.match(r",\s*an?\s+[^,.;]*", despues, re.I)
        if m and eco(m.group(0)):
            despues = despues[m.end():]
            while (m := re.match(r",\s*[^,.;]+", despues)) and eco(m.group(0)):
                despues = despues[m.end():]
            partes[k + 1] = despues
    return marca.join(partes)


def _aplicar_casting(prompt: str, fichas: dict[str, str],
                     breve: bool = False) -> tuple[str, list[str]]:
    """Cambia cada {CLAVE} por su ficha y devuelve el prompt y quién sale.

    Los personajes se deducen de las fichas que se sustituyeron de verdad, no
    de una lista aparte que declare el LLM: lo que cuenta es lo que acabó
    escrito en el prompt.
    """
    usados = []
    for clave, ficha in fichas.items():
        marca = "{" + clave + "}"
        # El modelo a veces escribe la clave pelada ("MADRASTRA stands alone…"):
        # quería referenciarla y se dejó las llaves. Sin esto la escena no se
        # marca, se genera sin su cara, y al generador de imagen le llega la
        # palabra MADRASTRA, que no significa nada. Las claves van en mayúsculas
        # y en español, así que confundirlas con una palabra del prompt (en
        # inglés y en minúscula) no pasa.
        prompt = re.sub(r"(?<!\{)\b" + re.escape(clave) + r"\b(?!\})", marca, prompt)
        if marca not in prompt:
            continue
        usados.append(clave)
        # La primera vez va la ficha; las siguientes, una referencia corta
        # ("the vintage robot"): el modelo usa el marcador como pronombre ("push
        # {X}. {X} resists…") y pegar la ficha entera cada vez la duplicaría.
        primera = _breve(ficha) if breve else ficha
        luego = "the " + re.sub(r"^(?:an?|the)\s+", "", _breve(ficha), flags=re.I)
        antes, *resto = _quitar_eco(prompt, marca, ficha).split(marca)
        prompt = antes + primera + luego.join(resto)
    # Sin marcador, pero con su descripción: el modelo lo describió a mano
    # ("a bulky beige mobile phone…") y sigue siendo él, así que la escena se
    # marca para que se genere con su referencia.
    usados += [c for c in detectar_personajes(prompt, fichas) if c not in usados]
    # Un marcador huérfano llegaría tal cual al generador de imagen, que lo
    # dibujaría como texto o lo tomaría por un dynamic prompt de ComfyUI. Se le
    # quitan las llaves y se deja dentro lo que hubiera.
    return _MARCADOR.sub(r"\1", prompt), usados


def detectar_personajes(prompt: str, fichas: dict[str, str]) -> list[str]:
    """Qué personajes del reparto salen en un prompt ya escrito.

    Los prompts se guardan con la ficha sustituida, así que quién sale se puede
    leer del propio texto. Hace falta al guardar prompts editados a mano: si
    metes a alguien en una escena (o lo quitas), lo que decidió el LLM al
    generarla deja de valer, y sin esto la escena seguiría generándose sin su
    cara. Se acepta también la forma abreviada, que es la que va en el prompt de
    movimiento.
    """
    return [
        clave
        for clave, ficha in fichas.items()
        if ficha and (ficha in prompt or _breve(ficha) in prompt)
    ]


def _lista_reparto(fichas: dict[str, str]) -> str:
    return "\n".join(f"- {{{clave}}}: {ficha}" for clave, ficha in fichas.items())


def _bloque_casting(fichas: dict[str, str]) -> str:
    """Instrucción de reparto para el prompt de escena. Vacía si no hay."""
    if not fichas:
        return ""
    return (
        "\n\nRecurring cast of this video:\n"
        f"{_lista_reparto(fichas)}\n\n"
        "When one of them is the subject of the current segment, refer to them "
        "in both prompts by writing their marker exactly as shown (including "
        "the braces) instead of describing their appearance. Each marker is "
        "replaced with the description above before the image is generated, so "
        "do not repeat, rephrase or contradict those physical details, and do "
        "not invent markers that are not in this list. The marker already is a "
        "complete noun phrase with its article: write \"{CLAVE} rolls forward\", "
        "never \"a robot {CLAVE}\" or \"{CLAVE}, a robot with…\". Spend your "
        "words on what the description does not cover — action, setting, "
        "framing, lighting, mood. If the segment shows none of them, use no "
        "marker."
    )


def _storyboard(system: str, titulo: str, guion_texto: str, estilo: str,
                segmentos: list[dict], fichas: dict[str, str]) -> StoryboardLLM:
    """Plan visual del video entero: un plano por segmento, en orden.

    El esquema no puede fijar cuántos planos vienen (cambia con cada video), así
    que se cuadra aquí: los que sobran se descartan y los que faltan quedan
    vacíos, y esa escena se escribe solo con su segmento, como antes.
    """
    lista = "\n".join(f"{i + 1}. {seg['texto']}" for i, seg in enumerate(segmentos))
    reparto = ""
    if fichas:
        reparto = (
            "\n\nRecurring cast of this video (refer to them only by their "
            "marker, braces included):\n" + _lista_reparto(fichas)
        )
    user = (
        f"Full video context:\n```markdown\n{titulo}\n{guion_texto}\n```\n\n"
        f"Template visual style: {estilo}{reparto}\n\n"
        f"Voice-over segments — write exactly {len(segmentos)} shots, one per "
        f"segment, in this order:\n{lista}"
        f"{_solo_json('mundo')}"
    )
    sb = llm.chat(system, user, StoryboardLLM)
    vacio = PlanoLLM(camara="-", accion="-")
    planos = (sb.planos + [vacio] * len(segmentos))[:len(segmentos)]
    return StoryboardLLM(mundo=sb.mundo, planos=planos)


def _bloque_storyboard(sb: StoryboardLLM, i: int) -> str:
    """El plano de la escena i, con sus vecinos para la continuidad.

    Un plano vacío (el storyboard se quedó corto) no se menciona: la escena
    sin plano se escribe solo con su segmento.
    """
    if sb.planos[i].accion == "-":
        return ""
    n = len(sb.planos)
    lineas = []
    for j, etiqueta in ((i - 1, "Previous shot"),
                        (i, f"THIS SHOT ({i + 1} of {n})"),
                        (i + 1, "Next shot")):
        if 0 <= j < n and sb.planos[j].accion != "-":
            p = sb.planos[j]
            lineas.append(f"{etiqueta}: {p.camara} — {p.accion}")
    return (
        f"\n\nVisual world of this video: {sb.mundo}\n\n"
        "Storyboard:\n" + "\n".join(lineas)
    )


def _storyboard_motion(system: str, titulo: str, guion_texto: str, estilo: str,
                       fs: list[dict]) -> StoryboardMotionLLM:
    """El plan del vídeo entero: cómo se corta la narración y qué se ve.

    A diferencia del storyboard de las demás plantillas, este decide también
    **la duración** de cada escena: agrupa frases, y las frases ya traen sus
    tiempos del audio (ver `_motion_frases`).
    """
    dura = fs[-1]["t_fin"] - fs[0]["t_inicio"] if fs else 0.0
    user = (
        f"Full video context:\n```markdown\n{titulo}\n{guion_texto}\n```\n\n"
        f"Template visual style: {estilo}\n\n"
        f"The narration, sentence by sentence — {len(fs)} sentences, "
        f"{dura:.0f}s in all. Group them into shots, in order, covering every "
        f"one:\n{_motion_frases.numeradas(fs)}"
        f"{_solo_json('idea')}"
    )
    return llm.chat(system, user, StoryboardMotionLLM)


def _planos_motion(sb: StoryboardMotionLLM, grupos: list[dict],
                   guion_texto: str) -> tuple[list[dict], dict]:
    """Los planos ya emparejados con las escenas que de verdad salieron.

    El reparto de frases puede fundir dos planos o partir uno en dos tomas, así
    que esta lista no es la del storyboard: es la de después.
    """
    crudos = [sb.planos[g["plano"]] for g in grupos]
    planos, fallos = _motion_ficha.revisar_planos(
        crudos, len(grupos), bool(re.search(r"\d", guion_texto)))
    for i, (g, crudo) in enumerate(zip(grupos, crudos)):
        # La primera toma no continúa nada: no hay nada en pantalla todavía.
        planos[i]["continua"] = bool(i and (g.get("sigue") or crudo.continua))
        planos[i]["muestra"] = (crudo.muestra or "").strip()
    return planos, fallos


def _ya_en_pantalla(previa: dict | None) -> str:
    """El dibujo que la escena hereda, escrito para que lo lea el modelo."""
    if not previa or not previa.get("piezas"):
        return ""
    lineas = []
    for p in previa["piezas"]:
        detalle = f", {p['ranuras']} ranuras, {p['llenas']} llenas" if p["ranuras"] else ""
        lineas.append(f"- {p['id']} ({p['tipo']}{detalle}, {p['estado']}) «{p['nombre']}»")
    for v in previa.get("vinculos", []):
        lineas.append(f"- {v['de']} → {v['a']} ({v['coste']})")
    return ("\n\nThis shot continues the previous one. Already on screen, and "
            "staying there unless you change it:\n" + "\n".join(lineas) +
            "\nDeclare only what is new or what changes.")


def _composiciones_motion(pl: dict, titulo: str, guion_texto: str,
                          sb: StoryboardMotionLLM, planos: list[dict],
                          segmentos: list[dict],
                          total: int) -> tuple[list[dict], dict]:
    """Una composición por escena: el dibujo y la tarjeta, ya reparados.

    Los planos se reparan **antes** de pedir nada (lo hace `_planos_motion`):
    el bloque decide qué clase de frase se escribe, y arreglarlo después deja
    frases enteras metidas en etiquetas de tres palabras (ver `_motion_ficha`).
    El dibujo, en cambio, se repara escena a escena, porque el de cada una
    depende de lo que dejara en pantalla la anterior.
    """
    system = pl["prompts"]["escena"]
    fallos = {}
    crudas, dibujos, previa = [], [], None
    for i, seg in enumerate(segmentos):
        parada.comprobar(f"quedaban {len(segmentos) - i} escenas")
        progreso.lote(i + 1, total, "escena")
        vecinos = []
        for j, etiqueta in ((i - 1, "Previous shot"),
                            (i, f"THIS SHOT ({i + 1} of {len(segmentos)})"),
                            (i + 1, "Next shot")):
            if 0 <= j < len(planos):
                p = planos[j]
                vecinos.append(f"{etiqueta}: {p['camara']} — {p['accion']}"
                               + (f" — {p['muestra']}" if p["muestra"] else ""))
        # Las frases de la toma, numeradas. Hay un titular por frase y se
        # relevan con la voz, así que pedirlas una a una es lo único que hace
        # que salgan tantos titulares como frases: con el segmento en prosa, el
        # modelo escribe uno y se queda tan ancho.
        frases = seg.get("frases") or [{"texto": seg["texto"]}]
        numeradas = "\n".join(f"{k + 1}. {fr['texto']}"
                              for k, fr in enumerate(frases))
        # El último titular anterior va en el mensaje: sin él el modelo repite
        # la frase del guion dos planos seguidos, porque el guion la repite.
        tarjeta = ""
        ultimo = next((tt.texto for tt in reversed(crudas[-1].titulares)
                       if (tt.texto or "").strip()), "") if crudas else ""
        if ultimo:
            tarjeta = ("\n\nThe headline the viewer is reading right now, at the "
                       f"end of the previous shot: «{ultimo}». Do not repeat it.")
        user = (
            f"Full video context:\n```markdown\n{titulo}\n{guion_texto}\n```\n\n"
            f"This shot's voice-over, sentence by sentence — write exactly "
            f"{len(frases)} titulares, one per sentence and in this order:"
            f"\n{numeradas}\n\n"
            f"Template visual style: {pl['estilo_visual']}\n\n"
            f"What the whole video explains: {sb.idea}\n\nStoryboard:\n"
            + "\n".join(vecinos)
            + (_ya_en_pantalla(previa) if planos[i]["continua"] else "")
            + tarjeta + _solo_json("titulares")
        )
        cruda = llm.chat(system, user, ComposicionLLM)
        dibujo, fallo = _motion_ficha.revisar_dibujo(cruda, planos[i], previa)
        for k, v in fallo.items():
            fallos[k] = fallos.get(k, 0) + v
        crudas.append(cruda)
        dibujos.append(dibujo)
        previa = dibujo

    fichas, fallos_ficha = _motion_ficha.revisar_fichas(
        crudas, planos, segmentos, guion_texto)
    return [f | d for f, d in zip(fichas, dibujos)], fallos | fallos_ficha


def _generar_motion(proyecto_id: int, pl: dict, titulo: str, guion_texto: str,
                    palabras: list[dict]) -> str:
    """Las escenas de una plantilla de motion: el corte y la composición.

    Aquí la narración no se trocea con una regla de reloj. Se parte en frases
    y es el storyboard el que dice cuántas van juntas en cada toma, así que las
    escenas duran lo que dura su idea y la suma sigue cuadrando con el audio.
    """
    fs = _motion_frases.frases(palabras)
    if not fs:
        raise ValueError("No se pudieron sacar frases de las palabras")

    # El storyboard cuenta como un paso más de la barra: es la llamada larga.
    progreso.lote(0, len(fs) + 1, "escena")
    sb = _storyboard_motion(pl["prompts"]["storyboard"], titulo, guion_texto,
                            pl["estilo_visual"], fs)
    grupos, fallos_frases = _motion_frases.repartir(fs, [p.frases for p in sb.planos])
    segmentos = _motion_frases.segmentos(fs, grupos, palabras[-1]["end"])
    planos, fallos_planos = _planos_motion(sb, grupos, guion_texto)
    composiciones, fallos = _composiciones_motion(
        pl, titulo, guion_texto, sb, planos, segmentos, len(segmentos) + 1)

    escenas = [
        seg | {
            "orden": i,
            # Lo que se lee en pantalla define la escena, así que va donde en
            # las demás plantillas va el prompt visual: es lo que la UI lista y
            # lo que se puede corregir a mano. Un titular por línea, en el
            # orden en que se dicen; los tiempos se quedan en la ficha.
            "prompt": "\n".join(tt["texto"] for tt in c["titulares"]),
            "prompt_movimiento": "",
            "ficha": json.dumps(c, ensure_ascii=False),
            "personajes": "",
            # Cada escena trae su dibujo: no hay semilla de mundo que repartir.
            "seed": 0,
        }
        for i, (seg, c) in enumerate(zip(segmentos, composiciones))
    ]
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        escenas_repo.reemplazar_todas(s, proyecto_id, escenas)
        avanzar_estado(p, "ESCENAS")
        s.commit()

    reparados = sum(fallos.values()) + sum(fallos_planos.values()) \
        + sum(fallos_frases.values())
    dur = [e["t_fin"] - e["t_inicio"] for e in escenas]
    return (f"{len(escenas)} escenas de {min(dur):.1f} a {max(dur):.1f}s"
            + (f" ({reparados} correcciones)" if reparados else ""))


def generar_escenas(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        meta_row = metadatos_repo.ultimo(s, proyecto_id)
        slug, plantilla = p.slug, p.plantilla
        fichas = personajes_repo.fichas(s, proyecto_id)

    palabras_path = PROYECTOS_DIR / slug / "palabras.json"
    if not palabras_path.exists():
        raise ValueError("No hay palabras.json; genera la voz y subtítulos primero")
    palabras = json.loads(palabras_path.read_text())

    g = json.loads(guion_row.contenido)
    guion_texto = guiones_repo.texto_narrado(g)
    titulo = ""
    if meta_row:
        titulo = json.loads(meta_row.contenido)["youtube"]["titulo"]

    pl = plantillas_repo.cargar(plantilla)
    if pl.get("montaje") == "motion":
        return _generar_motion(proyecto_id, pl, titulo, guion_texto, palabras)

    segmentos = _segmentar(palabras, pl["ritmo"]["duracion_escena_s"])
    if not segmentos:
        raise ValueError("No se pudieron segmentar las palabras")

    # El storyboard cuenta como un paso más de la barra: es la llamada larga.
    total = len(segmentos) + 1
    progreso.lote(0, total, "escena")
    sb = _storyboard(pl["prompts"]["storyboard"], titulo, guion_texto,
                     pl["estilo_visual"], segmentos, fichas)

    system = pl["prompts"]["escena"]
    casting = _bloque_casting(fichas)
    escenas = []
    for i, seg in enumerate(segmentos):
        parada.comprobar(f"quedaban {len(segmentos) - i} escenas")
        progreso.lote(i + 1, total, "escena")
        user = (
            f"Full video context:\n```markdown\n{titulo}\n{guion_texto}\n```\n\n"
            f"Current voice-over segment:\n```markdown\n{seg['texto']}\n```\n\n"
            f"Template visual style: {pl['estilo_visual']}"
            f"{_bloque_storyboard(sb, i)}"
            f"{casting}"
            f"{_solo_json('prompt')}"
        )
        r = llm.chat(system, user, EscenaLLM)
        # El prompt se guarda ya sustituido: lo que se lee en la UI es lo que
        # se le manda al generador, y sigue siendo editable a mano.
        prompt, quienes = _aplicar_casting(r.prompt, fichas)
        movimiento, _ = _aplicar_casting(r.prompt_movimiento, fichas, breve=True)
        escenas.append(seg | {
            "orden": len(escenas),
            "prompt": prompt,
            "prompt_movimiento": movimiento,
            "personajes": ",".join(quienes),
            "seed": random.randint(0, 2**31 - 1),
        })

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        escenas_repo.reemplazar_todas(s, proyecto_id, escenas)
        avanzar_estado(p, "ESCENAS")
        s.commit()
    return f"{len(escenas)} escenas con prompt visual y de movimiento"
