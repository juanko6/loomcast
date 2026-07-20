from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    tema_id: Mapped[int] = mapped_column(ForeignKey("temas.id"))
    titulo: Mapped[str] = mapped_column(Text)
    gancho: Mapped[str] = mapped_column(Text, default="")
    resumen: Mapped[str] = mapped_column(Text, default="")
    # propuesta | aprobada | descartada
    estado: Mapped[str] = mapped_column(default="propuesta")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
