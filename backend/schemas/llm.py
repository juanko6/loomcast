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


class MetadatosYouTubeLLM(BaseModel):
    titulo: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    etiquetas: list[str] = Field(min_length=1)


class MetadatosTikTokLLM(BaseModel):
    descripcion: str = Field(min_length=1)


class MetadatosLLM(BaseModel):
    youtube: MetadatosYouTubeLLM
    tiktok: MetadatosTikTokLLM
