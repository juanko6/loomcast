from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc

# Texto de calibración que narra el clip de referencia de cada voz del banco
# (neutro, con pregunta y números para capturar entonación variada).
REF_TEXT = (
    "Esta es la voz oficial de este canal. ¿Lista para contar una historia "
    "increíble? Empezamos en 3, 2, 1."
)


class Voz(Base):
    __tablename__ = "voces"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    nombre: Mapped[str] = mapped_column()
    # Descripción en lenguaje natural con la que VoiceDesign creó la voz
    instruct: Mapped[str] = mapped_column(Text)
    ref_text: Mapped[str] = mapped_column(Text, default=REF_TEXT)
    # generando | lista | error
    estado: Mapped[str] = mapped_column(default="generando")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
