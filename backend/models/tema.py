from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Tema(Base):
    __tablename__ = "temas"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    plantilla: Mapped[str] = mapped_column(default="curiosidades")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
