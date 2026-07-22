from sqlalchemy.orm import Session

from ..models import Ajuste


def leer(s: Session, clave: str) -> str | None:
    ajuste = s.get(Ajuste, clave)
    return ajuste.valor if ajuste else None


def escribir(s: Session, clave: str, valor: str) -> None:
    ajuste = s.get(Ajuste, clave)
    if ajuste is None:
        s.add(Ajuste(clave=clave, valor=valor))
    else:
        ajuste.valor = valor
