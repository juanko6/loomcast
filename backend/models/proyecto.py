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
    # Slug de la voz del banco elegida para narrar este proyecto
    voz: Mapped[str | None] = mapped_column(default=None)
    # Pista de música de este proyecto (fila de `musicas`). Vive en la
    # biblioteca de Música como cualquier otra pista, para poder escucharla y
    # descargarla sola, sin la narración: es el audio reutilizable en redes.
    # None = el proyecto no tiene música.
    musica_id: Mapped[int | None] = mapped_column(
        ForeignKey("musicas.id"), default=None
    )
    # Si el armado mezcla esa pista por debajo de la voz (con ducking). Tener
    # música y mezclarla son decisiones distintas: lo normal es querer la pista
    # aparte, y el vídeo con música es opcional.
    musica_mezclar: Mapped[bool] = mapped_column(default=False)
    estado: Mapped[str] = mapped_column(default="IDEA")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


def avanzar_estado(proyecto: Proyecto, nuevo: str) -> None:
    """El estado solo avanza (re-ejecutar una etapa no lo retrocede)."""
    if ORDEN_ESTADOS.index(nuevo) > ORDEN_ESTADOS.index(proyecto.estado):
        proyecto.estado = nuevo
