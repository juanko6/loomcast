"""El guion de secciones medido en compases, y la duración que sale de él.

En una pista de álbum la duración no la elige nadie: la pone lo que la pista
tiene que contar. El LLM escribe cada sección con sus compases
(`[Theme A - 16 bars - el saxo expone el tema]`) y de ahí sale cuánto dura la
pista. Que la duración que recibe ACE-Step cuadre con el guion es lo que evita
los dos males: que se corte antes de llegar al final, y que le sobre tiempo y lo
rellene repitiendo vueltas.

Funciones puras, sin base ni LLM: las usan el pipeline del álbum (validar lo
que devuelve el LLM), el servicio (recalcular al cambiar el tempo) y el
generador (quitar los compases antes de mandar el guion a ACE-Step).
"""
import re

# "16 bars", "8 bar", "12 compases": el número de compases dentro del marcador.
_COMPASES = re.compile(r"(\d{1,3})\s*(?:bars?|compases?|measures?)\b", re.I)
# El segmento entero, con el guion que lo separa, para quitarlo limpio:
# "[Theme A - 16 bars - texto]" → "[Theme A - texto]".
_SEGMENTO = re.compile(
    r"\s*[-–—,]?\s*\(?\d{1,3}\s*(?:bars?|compases?|measures?)\)?(?=\s*[-–—,\]])", re.I
)
_MARCADOR = re.compile(r"\[([^\]]+)\]")

# Segundos que se añaden tras el último compás para que el acorde final suene y
# se apague, en vez de cortarse a pelo.
COLA_S = 4
# Una sección más larga que esto es una vuelta estirada, salvo que sea un solo.
MAX_COMPASES_SECCION = 32
# Lo mismo medido en tiempo, que es lo que oye ACE-Step (los compases no le
# llegan): una sección es un momento, y pasado esto el modelo la rellena dando
# vueltas a lo mismo. Es lo que separó la pista que gustó (secciones de ~17 s)
# de las que se hicieron sosas (35-40 s cada una). Un solo tiene algo más.
MAX_S_SECCION = 25
MAX_S_SOLO = 35
# Más de esto seguidas con la misma longitud es la forma cuadrada.
MAX_IGUALES_SEGUIDAS = 2
# Nombres que cuentan como final compuesto.
_FINALES = ("outro", "ending", "coda", "final", "fin", "cierre")
_SOLOS = ("solo", "improvis")


def secciones(lyrics: str) -> list[tuple[str, int | None]]:
    """[(marcador sin compases, compases o None)] en el orden del guion."""
    out = []
    for m in _MARCADOR.finditer(lyrics or ""):
        dentro = m.group(1)
        c = _COMPASES.search(dentro)
        limpio = _SEGMENTO.sub("", f"[{dentro}]")[1:-1].strip(" -–—,")
        out.append((limpio, int(c.group(1)) if c else None))
    return out


def quitar_compases(lyrics: str) -> str:
    """El guion tal como lo recibe ACE-Step: los mismos marcadores sin el
    recuento de compases, que es para nosotros y no para el modelo (el formato
    con el que se validó el brief no lo llevaba)."""
    return _MARCADOR.sub(
        lambda m: "[" + _SEGMENTO.sub("", f"[{m.group(1)}]")[1:-1].strip(" -–—,") + "]",
        lyrics or "",
    )


def tiempos_por_compas(timesig: str) -> int:
    """Pulsos por compás al tempo dado. En 6 se cuentan seis (el bpm de ACE se
    toma como el de la corchea); es el caso raro y lo peor que pasa es una cola
    algo más larga o corta."""
    try:
        return max(1, int(timesig))
    except (TypeError, ValueError):
        return 4


def total_compases(lyrics: str) -> int:
    return sum(c or 0 for _, c in secciones(lyrics))


def duracion_desde_guion(lyrics: str, bpm: int, timesig: str) -> int | None:
    """Segundos que dura el guion, o None si no trae compases."""
    total = total_compases(lyrics)
    if total <= 0 or bpm <= 0:
        return None
    return round(total * tiempos_por_compas(timesig) * 60 / bpm) + COLA_S


def _nombre(marcador: str) -> str:
    return marcador.split("-")[0].strip().lower()


def segundos_por_compas(bpm: int, timesig: str) -> float:
    return tiempos_por_compas(timesig) * 60 / bpm


def problemas(lyrics: str, bpm: int | None = None, timesig: str = "4") -> list[str]:
    """Qué incumple el guion de una pista de álbum. Lista vacía = vale.

    Son las reglas contra el aburrimiento: cada sección medida, ninguna vuelta
    estirada, nunca dos secciones seguidas iguales, nada de bloques cuadrados y
    un final que se compone. Con el tempo, además, cada sección tiene que caber
    en un momento: una pista larga lleva más secciones, no más largas.
    """
    secs = secciones(lyrics)
    if len(secs) < 3:
        return ["el guion necesita al menos tres secciones (intro, cuerpo y final)"]
    out = []
    sin = [m for m, c in secs if not c]
    if sin:
        out.append(f"secciones sin compases: {', '.join(sin[:3])}")
    spc = segundos_por_compas(bpm, timesig) if bpm and bpm > 0 else None
    for m, c in secs:
        if not c:
            continue
        solo = any(s in m.lower() for s in _SOLOS)
        if c > MAX_COMPASES_SECCION and not solo:
            out.append(f"«{m}» dura {c} compases: es una vuelta estirada")
        elif spc and c * spc > (MAX_S_SOLO if solo else MAX_S_SECCION):
            tope = MAX_S_SOLO if solo else MAX_S_SECCION
            out.append(
                f"«{m}» dura {c * spc:.0f} s ({c} compases a {bpm} bpm) y el máximo "
                f"es {tope} s: pártela en momentos más cortos donde el lead haga algo nuevo"
            )
    for (a, _), (b, _) in zip(secs, secs[1:]):
        if a.strip().lower() == b.strip().lower():
            out.append(f"«{a}» se repite seguida sin cambiar nada")
    largos = [c for _, c in secs]
    for i in range(len(largos) - MAX_IGUALES_SEGUIDAS):
        tramo = largos[i : i + MAX_IGUALES_SEGUIDAS + 1]
        if tramo[0] and len(set(tramo)) == 1:
            out.append(
                f"{len(tramo)} secciones seguidas de {tramo[0]} compases: forma cuadrada, "
                "varía la longitud de las frases"
            )
            break
    if not any(f in _nombre(secs[-1][0]) for f in _FINALES):
        out.append("la última sección no es un final (outro, ending, coda)")
    return out
