import json

from sqlalchemy.orm import Session

from ..models import Guion


def texto_narrado(g: dict) -> str:
    """Texto que se narra/usa como contexto, sea cual sea el formato del guion.

    - Formato "narracion": gancho + párrafo continuo + cta.
    - Formato "frases": gancho + frases + cta (comportamiento clásico).

    En ambos el gancho abre y el cta cierra; solo cambia el cuerpo.
    """
    narracion = (g.get("narracion") or "").strip()
    if narracion:
        cuerpo = [narracion]
    else:
        cuerpo = list(g.get("frases", []))
    partes = [g.get("gancho", ""), *cuerpo, g.get("cta", "")]
    return " ".join(p.strip() for p in partes if p and p.strip())


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
