"""Contratos Pydantic por ámbito: API HTTP, LLMs y plantillas."""
from .api import (
    EscenaPromptIn,
    EscenasIn,
    EstadoIdeaIn,
    GuionIn,
    TemaIn,
    VideoIn,
    VozNuevaIn,
    VozSeleccionIn,
)
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
    "EscenaPromptIn", "EscenasIn", "EstadoIdeaIn", "GuionIn", "TemaIn",
    "VideoIn", "VozNuevaIn", "VozSeleccionIn",
    "DescripcionLLM", "EscenaLLM", "EtiquetasLLM",
    "GuionLLM", "IdeaLLM", "IdeasLLM", "TituloLLM",
    "Plantilla", "RitmoPlantilla", "SubtitulosPlantilla", "VozPlantilla",
]
