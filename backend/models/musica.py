from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Musica(Base):
    """Una pista de música generada con ACE-Step vía ComfyUI, independiente del
    pipeline de video. Cubre los tres usos con dos modos:
      - `tipo="instrumental"`: música de fondo / jingle (sin voz), solo `tags`.
      - `tipo="cancion"`: canción con voz cantada, `tags` + `lyrics` con
        marcadores [verse]/[chorus].

    El ciclo de vida vive en `estado`: nueva (idea + campos editables) →
    generada (el archivo de audio existe en disco). La ayuda del LLM es opcional
    (rellena tags/lyrics desde la idea) y no cambia el estado.
    """

    __tablename__ = "musicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    # instrumental | cancion
    tipo: Mapped[str] = mapped_column(default="instrumental")
    # Lo que escribió el usuario (español): la idea/ambiente de la pista.
    idea: Mapped[str] = mapped_column(Text)
    # Etiquetas de estilo para ACE-Step (inglés, coma-separadas). None hasta que
    # el usuario las escribe o el LLM las sugiere.
    tags: Mapped[str | None] = mapped_column(Text, default=None)
    # Letra con marcadores [verse]/[chorus] (solo tipo=cancion). None/"" en
    # instrumental.
    lyrics: Mapped[str | None] = mapped_column(Text, default=None)
    # Duración objetivo en segundos (placeholder {DURACION} del workflow).
    duracion_s: Mapped[int] = mapped_column(default=30)
    # Seed de la última generación (None hasta generar).
    seed: Mapped[int | None] = mapped_column(default=None)
    # nueva | generada
    estado: Mapped[str] = mapped_column(default="nueva")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
