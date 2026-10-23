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


def _cuerpo(g: dict) -> list[str]:
    """El cuerpo del guion como lista de textos, en cualquiera de los formatos."""
    lineas = g.get("lineas") or []
    if lineas:
        return [
            sin_etiqueta(normalizar_clave(x.get("personaje") or ""), x.get("texto") or "")
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
        (clave, sin_etiqueta(clave, x.get("texto") or ""))
        for clave, x in (
            (normalizar_clave(x.get("personaje") or ""), x) for x in lineas
        )
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
        {"personaje": clave, "texto": sin_etiqueta(clave, x.get("texto") or "")}
        for clave, x in (
            (normalizar_clave(x.get("personaje") or ""), x) for x in lineas
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
