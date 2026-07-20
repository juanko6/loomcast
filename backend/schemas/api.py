"""Contratos de la API HTTP (entrada de los routers)."""
from pydantic import BaseModel


class TemaIn(BaseModel):
    texto: str
    plantilla: str = "curiosidades"


class EstadoIdeaIn(BaseModel):
    estado: str  # propuesta | aprobada | descartada


class GuionIn(BaseModel):
    gancho: str
    frases: list[str]
    cta: str
