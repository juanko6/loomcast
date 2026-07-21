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


class VozNuevaIn(BaseModel):
    nombre: str
    instruct: str


class VozSeleccionIn(BaseModel):
    voz: str  # slug de la voz del banco


class EscenaPromptIn(BaseModel):
    orden: int
    prompt: str


class EscenasIn(BaseModel):
    escenas: list[EscenaPromptIn]


class VideoIn(BaseModel):
    modo: str = "kenburns"  # estatico | kenburns
