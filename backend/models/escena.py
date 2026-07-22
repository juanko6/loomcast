from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Escena(Base):
    __tablename__ = "escenas"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    orden: Mapped[int] = mapped_column()
    t_inicio: Mapped[float] = mapped_column()
    t_fin: Mapped[float] = mapped_column()
    # Texto del segmento de voz en off que cubre la escena
    texto: Mapped[str] = mapped_column(Text)
    # Prompt visual en inglés generado por el LLM
    prompt: Mapped[str] = mapped_column(Text)
    # Prompt de movimiento en inglés para el modo i2v (qué se mueve en la
    # escena). El prompt visual describe una imagen fija y no dirige movimiento.
    prompt_movimiento: Mapped[str] = mapped_column(Text, default="")
    seed: Mapped[int] = mapped_column(default=0)
    # Modo con el que se quiere animar esta escena (estatico|kenburns|i2v).
    # Vacío = usar el modo global que se elija al generar el video.
    modo: Mapped[str] = mapped_column(default="")
    # Modo con el que se generó el clip que hay ahora en clips/, para saber qué
    # se está mirando cuando el video mezcla modos.
    clip_modo: Mapped[str] = mapped_column(default="")
    # Duración del último render, en segundos (0 = nunca medido).
    imagen_s: Mapped[float] = mapped_column(default=0.0)
    clip_s: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
