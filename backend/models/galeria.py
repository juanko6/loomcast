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

    El tipo `animada` sigue igual hasta elegir preview, pero la elegida no pasa
    por ESRGAN (el vídeo se anima a resolución baja y el escalado se hace sobre
    el vídeo) y el ciclo sigue: final → movimiento (prompt de movimiento
    guardado) → animada (loop.mp4 listo) → escalada (hay versión 2K o 4K).
    """

    __tablename__ = "imagenes_libres"

    id: Mapped[int] = mapped_column(primary_key=True)
    # generar | editar | quitarfondo | animada
    tipo: Mapped[str] = mapped_column(default="generar")
    # Id del motor de [imagen.motores] de config.toml con el que se generan las
    # previews (Z-Image, FLUX.2 Klein, Qwen-Image-Edit…). Vacío = el motor por
    # defecto del modo. No aplica a quitarfondo, que no pasa por ComfyUI.
    motor: Mapped[str] = mapped_column(default="")
    # Lo que escribió el usuario (español): idea a generar o cambios a aplicar.
    idea: Mapped[str] = mapped_column(Text)
    # Prompt en inglés que produce el LLM y que el usuario puede editar; None
    # hasta que termina la etapa de mejora.
    prompt: Mapped[str | None] = mapped_column(Text, default=None)
    width: Mapped[int] = mapped_column(default=768)
    height: Mapped[int] = mapped_column(default=1344)
    # nueva | mejorada | previews | final [| movimiento | animada | escalada]
    estado: Mapped[str] = mapped_column(default="nueva")
    # Las 4 seeds de las previews, en JSON (mismo orden que preview_{i}.png).
    seeds: Mapped[str] = mapped_column(Text, default="[]")
    # Índice de la preview elegida para la versión final (None hasta elegir).
    seed_elegido: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
    # Solo `animada`. Lo que se mueve en el bucle, en inglés: lo escribe el
    # usuario y el LLM, si se le pide, lo pule sin cambiarle la intención.
    prompt_movimiento: Mapped[str] = mapped_column(Text, default="")
    # Duración del bucle en segundos (10–15); el LLM la recomienda al pulir.
    duracion_s: Mapped[int] = mapped_column(default=12)
    # Semilla del último vídeo animado (None hasta animar).
    seed_video: Mapped[int | None] = mapped_column(default=None)
    # Última versión escalada: None | "2k" | "4k".
    escala: Mapped[str | None] = mapped_column(default=None)
