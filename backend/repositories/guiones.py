import json

from sqlalchemy.orm import Session

from ..models import Guion
from .personajes import normalizar_clave


def _cuerpo(g: dict) -> list[str]:
    """El cuerpo del guion como lista de textos, en cualquiera de los formatos."""
    lineas = g.get("lineas") or []
    if lineas:
        return [(x.get("texto") or "").strip() for x in lineas]
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

    crudos = [("", g.get("gancho", ""))]
    crudos += [
        (normalizar_clave(x.get("personaje") or ""), x.get("texto") or "")
        for x in lineas
    ]
    crudos.append(("", g.get("cta", "")))

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
        {"personaje": normalizar_clave(x.get("personaje") or ""),
         "texto": (x.get("texto") or "").strip()}
        for x in lineas
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
