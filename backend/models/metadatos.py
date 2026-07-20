from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Metadatos(Base):
    __tablename__ = "metadatos"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    version: Mapped[int] = mapped_column(default=1)
    # JSON: {"youtube": {...}, "tiktok": {...}}
    contenido: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
