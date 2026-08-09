from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Musica(Base):
    """Una pista de música generada con ACE-Step 1.5 vía ComfyUI, independiente
    del pipeline de video. Cubre los tres usos con dos modos:
      - `tipo="instrumental"`: música de fondo / jingle (sin voz), solo `tags`.
      - `tipo="cancion"`: canción con voz cantada, `tags` + `lyrics` con
        marcadores [Verse 1 - ...]/[Chorus - ...].

    El ciclo de vida vive en `estado`: nueva (idea + campos editables) →
    generada (el archivo de audio existe en disco). La ayuda del LLM es opcional
    (rellena los campos desde la idea) y no cambia el estado.
    """

    __tablename__ = "musicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    # instrumental | cancion
    tipo: Mapped[str] = mapped_column(default="instrumental")
    # Lo que escribió el usuario (español): la idea/ambiente de la pista.
    idea: Mapped[str] = mapped_column(Text)
    # Descripción de estilo para ACE-Step 1.5 (inglés). Se llama `tags` porque
    # así se llama la entrada del nodo TextEncodeAceStepAudio1.5, pero el modelo
    # espera prosa: un párrafo con instrumentación, arreglo, mezcla y espacio.
    # None hasta que el usuario la escribe o el LLM la sugiere.
    tags: Mapped[str | None] = mapped_column(Text, default=None)
    # De dónde saca ACE-Step la estructura, en los dos modos: en canción es la
    # letra cantada con marcadores [Verse 1 - ...]; en instrumental, un guion de
    # secciones con solo marcadores y sin palabras. Vacío = un único bucle
    # repetido durante toda la pista.
    lyrics: Mapped[str | None] = mapped_column(Text, default=None)
    # Duración objetivo en segundos (placeholder {DURACION} del workflow).
    duracion_s: Mapped[int] = mapped_column(default=30)
    # Conditioning musical de ACE-Step 1.5, lo que v1 no tenía: sin tempo,
    # tonalidad y compás fijos el arreglo deriva y los instrumentos chocan.
    # Los tres se validan contra las listas del nodo en services/musica.py.
    bpm: Mapped[int] = mapped_column(default=120)
    # "<raíz> <major|minor>", p. ej. "C major" o "E minor".
    keyscale: Mapped[str] = mapped_column(default="C major")
    # Compás como cadena: "2" | "3" | "4" | "6" (el nodo usa un combo de texto).
    timesig: Mapped[str] = mapped_column(default="4")
    # Idioma de la letra en código ISO corto ("es", "en"…), de la lista del nodo.
    idioma: Mapped[str] = mapped_column(default="es")
    # Seed de la última generación (None hasta generar).
    seed: Mapped[int | None] = mapped_column(default=None)
    # nueva | generada
    estado: Mapped[str] = mapped_column(default="nueva")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
