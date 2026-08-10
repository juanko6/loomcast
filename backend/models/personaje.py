from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Personaje(Base):
    """Ficha física canónica de alguien que sale en varias escenas del vídeo.

    Existe porque cada escena se prompt-ea por separado: sin una descripción
    fija que se repita palabra por palabra, el LLM escribe "a young woman" en
    una escena y "a woman in her thirties" en otra, y el generador dibuja a dos
    personas distintas. La ficha se inyecta literal en cada prompt donde
    aparezca el personaje.
    """

    __tablename__ = "personajes"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    # Orden de aparición en el guion, para que la UI los liste estable.
    orden: Mapped[int] = mapped_column(default=0)
    # Token con el que el LLM lo referencia en los prompts de escena: {ANA}.
    # En mayúsculas y sin espacios.
    clave: Mapped[str] = mapped_column()
    # Cómo se le llama en el guion, para que la UI sea legible.
    nombre: Mapped[str] = mapped_column(default="")
    # Descripción física en inglés que se sustituye tal cual en el prompt.
    ficha: Mapped[str] = mapped_column(Text, default="")
    # Semilla propia: con el mismo sujeto y la misma seed las caras se parecen
    # más entre escenas, y es la que fijará el retrato de referencia.
    seed: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
