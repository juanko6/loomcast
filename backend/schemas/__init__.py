"""Contratos Pydantic por ámbito: API HTTP, LLMs y plantillas."""
from .api import EstadoIdeaIn, GuionIn, TemaIn
from .llm import (
    DescripcionLLM,
    EscenaLLM,
    EtiquetasLLM,
    GuionLLM,
    IdeaLLM,
    IdeasLLM,
    TituloLLM,
)
from .plantilla import (
    Plantilla,
    RitmoPlantilla,
    SubtitulosPlantilla,
    VozPlantilla,
)

__all__ = [
    "EstadoIdeaIn", "GuionIn", "TemaIn",
    "DescripcionLLM", "EscenaLLM", "EtiquetasLLM",
    "GuionLLM", "IdeaLLM", "IdeasLLM", "TituloLLM",
    "Plantilla", "RitmoPlantilla", "SubtitulosPlantilla", "VozPlantilla",
]
