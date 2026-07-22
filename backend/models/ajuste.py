from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Ajuste(Base):
    """Preferencias globales de la instancia (clave → valor).

    Viven en la BD y no en config.toml porque se cambian desde la UI y tienen
    que sobrevivir al reinicio del backend. Hoy solo guarda el modelo LLM
    activo (clave `llm_modelo`).
    """

    __tablename__ = "ajustes"

    clave: Mapped[str] = mapped_column(primary_key=True)
    valor: Mapped[str] = mapped_column(Text)
