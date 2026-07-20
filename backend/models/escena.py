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
    seed: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
