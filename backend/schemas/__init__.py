"""Contratos Pydantic por ámbito: API HTTP, LLMs y plantillas."""
from .api import EstadoIdeaIn, GuionIn, TemaIn
from .llm import (
    GuionLLM,
    IdeaLLM,
    IdeasLLM,
    MetadatosLLM,
    MetadatosTikTokLLM,
    MetadatosYouTubeLLM,
)
from .plantilla import (
    Plantilla,
    RitmoPlantilla,
    SubtitulosPlantilla,
    VozPlantilla,
)

__all__ = [
    "EstadoIdeaIn", "GuionIn", "TemaIn",
    "GuionLLM", "IdeaLLM", "IdeasLLM",
    "MetadatosLLM", "MetadatosTikTokLLM", "MetadatosYouTubeLLM",
    "Plantilla", "RitmoPlantilla", "SubtitulosPlantilla", "VozPlantilla",
]
