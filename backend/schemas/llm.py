"""Contratos de salida de los LLMs.

Cada modelo cumple doble función: genera el JSON schema que restringe la
generación en llama-server, y valida/parsea la respuesta al volver.
"""
from pydantic import BaseModel, Field, RootModel


class IdeaLLM(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    gancho: str = Field(min_length=1)
    resumen: str = Field(min_length=1)


class IdeasLLM(RootModel[list[IdeaLLM]]):
    root: list[IdeaLLM] = Field(min_length=1)


class GuionLLM(BaseModel):
    gancho: str = Field(min_length=1)
    frases: list[str] = Field(min_length=1)
    cta: str = Field(min_length=1)


class TituloLLM(BaseModel):
    # El prompt pide 35-55 chars (máx 65); el margen evita rechazar por poco
    titulo: str = Field(min_length=10, max_length=80)


class DescripcionLLM(BaseModel):
    # El prompt pide 250-450 chars; margen amplio para no rechazar por poco
    descripcion: str = Field(min_length=100, max_length=600)


class EtiquetasLLM(BaseModel):
    etiquetas: list[str] = Field(min_length=5, max_length=15)
    tiktok: str = Field(min_length=1, max_length=250)


class EscenaLLM(BaseModel):
    prompt: str = Field(min_length=20)
    # Qué se mueve en la escena; solo lo usa el modo i2v
    prompt_movimiento: str = Field(min_length=20)
