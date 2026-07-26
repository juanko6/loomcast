from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class ImagenLibre(Base):
    """Una generación de la galería de imágenes independiente del pipeline de
    video. Cubre los dos modos: crear una imagen desde una idea de texto
    (`tipo="generar"`) y editar una imagen subida con un prompt de cambios
    (`tipo="editar"`).

    El ciclo de vida vive en `estado`: nueva → mejorada (el LLM ya pulió el
    prompt) → previews (4 imágenes con distinta seed) → final (la elegida,
    ampliada con ESRGAN).
    """

    __tablename__ = "imagenes_libres"

    id: Mapped[int] = mapped_column(primary_key=True)
    # generar | editar
    tipo: Mapped[str] = mapped_column(default="generar")
    # Lo que escribió el usuario (español): idea a generar o cambios a aplicar.
    idea: Mapped[str] = mapped_column(Text)
    # Prompt en inglés que produce el LLM y que el usuario puede editar; None
    # hasta que termina la etapa de mejora.
    prompt: Mapped[str | None] = mapped_column(Text, default=None)
    width: Mapped[int] = mapped_column(default=768)
    height: Mapped[int] = mapped_column(default=1344)
    # nueva | mejorada | previews | final
    estado: Mapped[str] = mapped_column(default="nueva")
    # Las 4 seeds de las previews, en JSON (mismo orden que preview_{i}.png).
    seeds: Mapped[str] = mapped_column(Text, default="[]")
    # Índice de la preview elegida para la versión final (None hasta elegir).
    seed_elegido: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
