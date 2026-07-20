"""Contratos Pydantic de la API (entrada/salida HTTP)."""
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
