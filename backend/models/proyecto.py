from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc

ORDEN_ESTADOS = [
    "IDEA", "GUION", "METADATOS", "VOZ", "SUBTITULOS", "ESCENAS",
    "IMAGENES", "UPSCALE", "CLIPS", "INTERPOLADO", "FINAL",
]


class Proyecto(Base):
    __tablename__ = "proyectos"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"))
    slug: Mapped[str] = mapped_column(unique=True)
    plantilla: Mapped[str] = mapped_column(default="curiosidades")
    estado: Mapped[str] = mapped_column(default="IDEA")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


def avanzar_estado(proyecto: Proyecto, nuevo: str) -> None:
    """El estado solo avanza (re-ejecutar una etapa no lo retrocede)."""
    if ORDEN_ESTADOS.index(nuevo) > ORDEN_ESTADOS.index(proyecto.estado):
        proyecto.estado = nuevo
