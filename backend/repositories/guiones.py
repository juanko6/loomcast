import json
import re

from sqlalchemy.orm import Session

from ..models import Guion
from .personajes import normalizar_clave

# Cómo se cuela el nombre del personaje delante de su frase: "ANA ¿Y si soy yo
# la que no existe?", "VECINO: es tarde", "(NARRADOR) el hombre no se mueve".
# El prompt del guion lo prohíbe y el LLM lo escribe igual, y lo que se queda
# en el texto **se oye**: el TTS narra lo que hay, nombre incluido.
#
# Se quita aquí, donde el guion se normaliza, y no en la etapa de voz, para que
# el editor enseñe la línea tal y como se va a narrar.
_ETIQUETAS_NARRADOR = ("NARRADOR", "NARRADORA", "NARRACION", "NARRACIÓN")


def _etiqueta_quitada(clave: str, texto: str) -> str:
    """`texto` sin el nombre de su dueño delante, si lo llevaba.

    Solo se quita la etiqueta **de quien dice esa línea**, y solo cuando viene
    como etiqueta: en mayúsculas igual que la clave, o seguida de dos puntos,
    raya o punto. Una línea del narrador que empieza por "Ana decide borrar la
    mentira" no lleva etiqueta, lleva a Ana de sujeto, y quitarle el nombre se
    cargaría la frase.
    """
    for etiqueta in ((clave,) if clave else _ETIQUETAS_NARRADOR):
        if not etiqueta:
            continue
        # La clave lleva guion bajo donde el LLM escribe un espacio
        # (EL_VECINO → "EL VECINO Es tarde").
        patron = re.escape(etiqueta).replace("_", r"[\s_]+")
        m = re.match(
            rf"[(\[]?\s*({patron})\s*[)\]]?\s*([:：.]|[-–—])?\s+",
            texto, re.IGNORECASE,
        )
        if m and (m.group(1) == etiqueta or m.group(2)):
            return texto[m.end():].lstrip()
    return texto


def sin_etiqueta(clave: str, texto: str) -> str:
    """Como `_etiqueta_quitada`, pero por si viene repetida ("ANA: ANA …")."""
    texto = (texto or "").strip()
    for _ in range(2):
        limpio = _etiqueta_quitada(clave, texto)
        if limpio == texto:
            break
        texto = limpio
    return texto


# El nombre al principio de una línea **sin dueño**: "ANA: Es una broma",
# "MARC: Mira estas marcas". El LLM escribe el cuerpo en formato teatro en vez
# de poner la clave en su campo —se lo pide el prompt y lo ignora— y entonces
# pasan las dos cosas a la vez: la línea se queda sin quien la diga, así que la
# narra el narrador, y el nombre se oye en el audio.
#
# El nombre es lo único que dice quién habla, así que no se tira: se pasa al
# campo que le tocaba. Dos formas, y la segunda es la estricta a propósito:
# con dos puntos basta con que el nombre empiece por mayúscula ("Ana: …"),
# porque los dos puntos ya son la marca; sin ellos tiene que venir en
# MAYÚSCULAS y en una sola palabra ("ANA ¿Y si…"), que es como se escribe una
# acotación y no como empieza una frase normal del narrador.
_SUELTA_CON_DOS_PUNTOS = re.compile(
    r"[(\[]?\s*(?P<clave>[^\W\d_][\w'’-]*(?:[ _][^\W\d_][\w'’-]*){0,2})"
    r"\s*[)\]]?\s*[:：]\s+",
)
# Sin dos puntos se pide además que lo que sigue arranque como arranca una
# frase dicha —mayúscula o signo de apertura—: así "ANA ¿Y si…" y "VECINO Es
# tarde" entran, y un énfasis del narrador en mayúsculas ("ESTO no es de
# dentro") se queda donde está en vez de convertirse en un personaje.
_SUELTA_EN_MAYUSCULAS = re.compile(
    r"(?P<clave>[^\W\d_a-zà-öø-ÿ]{2,20})\s+(?=[^\W\d_a-zà-öø-ÿ]|[¿¡—–\"«'])"
)


def _dueño_suelto(texto: str) -> tuple[str, str]:
    """(clave, resto) si la línea lleva delante el nombre de quien la dice.

    Devuelve ("", texto) si no lo lleva, y también si lo que lleva delante es
    el propio narrador ("NARRADOR: …"): ese no es un personaje al que darle
    voz, es la etiqueta de que no hay ninguno.
    """
    for patron in (_SUELTA_CON_DOS_PUNTOS, _SUELTA_EN_MAYUSCULAS):
        m = patron.match(texto)
        if m is None:
            continue
        resto = texto[m.end():].lstrip()
        if not resto:
            continue
        clave = normalizar_clave(m.group("clave"))
        if not clave:
            continue
        if clave in _ETIQUETAS_NARRADOR:
            return "", resto
        return clave, resto
    return "", texto


def dueño_y_texto(clave: str, texto: str) -> tuple[str, str]:
    """Quién dice la línea y qué dice, con el nombre fuera del texto.

    Es el único sitio donde se decide eso, y lo usan los tres caminos: el guion
    que se guarda, el que lee el editor y los tramos que se narran.
    """
    texto = (texto or "").strip()
    if clave:
        return clave, sin_etiqueta(clave, texto)
    dueño, resto = _dueño_suelto(texto)
    if dueño:
        return dueño, resto
    return "", sin_etiqueta("", resto)


def _cuerpo(g: dict) -> list[str]:
    """El cuerpo del guion como lista de textos, en cualquiera de los formatos."""
    lineas = g.get("lineas") or []
    if lineas:
        return [
            dueño_y_texto(normalizar_clave(x.get("personaje") or ""),
                          x.get("texto") or "")[1]
            for x in lineas
        ]
    narracion = (g.get("narracion") or "").strip()
    if narracion:
        return [narracion]
    return list(g.get("frases", []))


def texto_narrado(g: dict) -> str:
    """Texto que se narra/usa como contexto, sea cual sea el formato del guion.

    - Formato "narracion": gancho + párrafo continuo + cta.
    - Formato "frases": gancho + frases + cta (comportamiento clásico).
    - Formato "lineas": gancho + el texto de cada línea en orden + cta. A quién
      se le atribuye cada línea no entra aquí: esto es lo que se oye, y es lo
      que esperan las escenas, la música y los metadatos.

    En los tres el gancho abre y el cta cierra; solo cambia el cuerpo.
    """
    partes = [g.get("gancho", ""), *_cuerpo(g), g.get("cta", "")]
    return " ".join(p.strip() for p in partes if p and p.strip())


def tramos(g: dict) -> list[tuple[str, str]]:
    """La narración partida en (clave_del_personaje, texto), en orden.

    Es lo que consume la etapa de voz para sintetizar cada tramo con la voz que
    le toca; la clave vacía es el narrador. Los formatos "frases" y "narracion"
    devuelven **un solo tramo** con el texto de `texto_narrado`, de modo que esa
    etapa hace exactamente la misma llamada al TTS que antes de que existiera
    esto: la voz por personaje no puede cambiar lo que ya sale bien.

    Los tramos seguidos del mismo dueño se unen. Importa por dos motivos: el
    narrador suena a frases cortadas si su párrafo se sintetiza a trozos, y cada
    llamada al modelo tiene su coste fijo.
    """
    lineas = g.get("lineas") or []
    if not lineas:
        texto = texto_narrado(g)
        return [("", texto)] if texto else []

    # La etiqueta se quita también aquí, y no solo al normalizar el guion:
    # esta es la última puerta antes del TTS y los guiones escritos antes de
    # que esto existiera siguen guardados con el nombre dentro del texto.
    crudos = [("", sin_etiqueta("", g.get("gancho", "")))]
    crudos += [
        dueño_y_texto(normalizar_clave(x.get("personaje") or ""),
                      x.get("texto") or "")
        for x in lineas
    ]
    crudos.append(("", sin_etiqueta("", g.get("cta", ""))))

    out: list[tuple[str, str]] = []
    for clave, texto in crudos:
        texto = texto.strip()
        if not texto:
            continue
        if out and out[-1][0] == clave:
            out[-1] = (clave, f"{out[-1][1]} {texto}")
        else:
            out.append((clave, texto))
    return out


def normalizar_lineas(contenido: dict) -> dict:
    """Deja las líneas atribuidas con claves válidas y sin tramos vacíos.

    La clave acaba siendo el marcador `{CLAVE}` del reparto, así que pasa por el
    mismo normalizador que el casting: lo que escriba el LLM al redactar la
    historia ("Ana", "ana ") y lo que se teclee en el editor tienen que casar con
    la clave del personaje, o la línea se quedaría sin voz.
    """
    lineas = contenido.get("lineas")
    if not lineas:
        return contenido
    limpias = [
        {"personaje": clave, "texto": texto}
        for clave, texto in (
            dueño_y_texto(normalizar_clave(x.get("personaje") or ""),
                          x.get("texto") or "")
            for x in lineas
        )
    ]
    return {**contenido, "lineas": [x for x in limpias if x["texto"]]}


def ultimo(s: Session, proyecto_id: int) -> Guion | None:
    return (
        s.query(Guion)
        .filter(Guion.proyecto_id == proyecto_id)
        .order_by(Guion.version.desc())
        .first()
    )


def crear(s: Session, proyecto_id: int, contenido: dict) -> Guion:
    """Crea la siguiente versión del guion (el versionado es automático)."""
    previo = ultimo(s, proyecto_id)
    g = Guion(
        proyecto_id=proyecto_id,
        version=(previo.version + 1) if previo else 1,
        contenido=json.dumps(contenido, ensure_ascii=False),
    )
    s.add(g)
    return g
