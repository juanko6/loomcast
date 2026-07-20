"""Modelos SQLAlchemy: temas, ideas, proyectos, guiones, metadatos, jobs."""
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


ORDEN_ESTADOS = [
    "IDEA", "GUION", "METADATOS", "VOZ", "SUBTITULOS", "ESCENAS",
    "IMAGENES", "UPSCALE", "CLIPS", "INTERPOLADO", "FINAL",
]


def avanzar_estado(proyecto: "Proyecto", nuevo: str) -> None:
    """El estado solo avanza (re-ejecutar una etapa no lo retrocede)."""
    if ORDEN_ESTADOS.index(nuevo) > ORDEN_ESTADOS.index(proyecto.estado):
        proyecto.estado = nuevo


class Tema(Base):
    __tablename__ = "temas"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(Text)
    plantilla: Mapped[str] = mapped_column(default="curiosidades")
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    tema_id: Mapped[int] = mapped_column(ForeignKey("temas.id"))
    titulo: Mapped[str] = mapped_column(Text)
    gancho: Mapped[str] = mapped_column(Text, default="")
    resumen: Mapped[str] = mapped_column(Text, default="")
    # propuesta | aprobada | descartada
    estado: Mapped[str] = mapped_column(default="propuesta")
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Proyecto(Base):
    __tablename__ = "proyectos"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"))
    slug: Mapped[str] = mapped_column(unique=True)
    plantilla: Mapped[str] = mapped_column(default="curiosidades")
    # IDEA → GUION → METADATOS → VOZ → SUBTITULOS → ESCENAS → IMAGENES
    # → UPSCALE → CLIPS → INTERPOLADO → FINAL
    estado: Mapped[str] = mapped_column(default="IDEA")
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Guion(Base):
    __tablename__ = "guiones"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    version: Mapped[int] = mapped_column(default=1)
    # JSON: {"gancho": str, "frases": [str], "cta": str}
    contenido: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Metadatos(Base):
    __tablename__ = "metadatos"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    version: Mapped[int] = mapped_column(default=1)
    # JSON: {"youtube": {...}, "tiktok": {...}}
    contenido: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # generar_ideas | generar_guion | generar_metadatos
    tipo: Mapped[str] = mapped_column()
    # id del tema o proyecto según el tipo
    ref_id: Mapped[int] = mapped_column()
    # pendiente | corriendo | ok | error
    estado: Mapped[str] = mapped_column(default="pendiente")
    log: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
