"""Contratos Pydantic por ámbito: API HTTP, LLMs y plantillas."""
from .api import (
    EscenaPromptIn,
    EscenasIn,
    GaleriaFinalIn,
    GaleriaGenerarIn,
    GaleriaPreviewsIn,
    GaleriaPromptIn,
    ModoEscenaIn,
    ModosEscenasIn,
    MusicaCamposIn,
    MusicaGenerarIn,
    MusicaLanzarIn,
    RegenerarClipIn,
    RegenerarImagenIn,
    EstadoIdeaIn,
    GuionIn,
    TemaIn,
    VideoIn,
    VozGenerarIn,
    VozNuevaIn,
    VozSeleccionIn,
)
from .llm import (
    DescripcionLLM,
    EscenaLLM,
    EtiquetasLLM,
    GuionLLM,
    GuionNarracionLLM,
    IdeaLLM,
    IdeasLLM,
    ImagenLibrePromptLLM,
    MusicaPromptLLM,
    TituloLLM,
)
from .plantilla import (
    Plantilla,
    RitmoPlantilla,
    SubtitulosPlantilla,
    VozPlantilla,
)

__all__ = [
    "EscenaPromptIn", "EscenasIn", "GaleriaFinalIn", "GaleriaGenerarIn",
    "GaleriaPreviewsIn", "GaleriaPromptIn", "ModoEscenaIn", "ModosEscenasIn",
    "MusicaCamposIn", "MusicaGenerarIn", "MusicaLanzarIn",
    "RegenerarClipIn", "RegenerarImagenIn", "EstadoIdeaIn", "GuionIn", "TemaIn",
    "VideoIn", "VozGenerarIn", "VozNuevaIn", "VozSeleccionIn",
    "DescripcionLLM", "EscenaLLM", "EtiquetasLLM",
    "GuionLLM", "GuionNarracionLLM", "IdeaLLM", "IdeasLLM",
    "ImagenLibrePromptLLM", "MusicaPromptLLM", "TituloLLM",
    "Plantilla", "RitmoPlantilla", "SubtitulosPlantilla", "VozPlantilla",
]
