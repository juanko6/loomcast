"""Contratos Pydantic: API HTTP, salidas de los LLMs y plantillas."""
from pydantic import BaseModel, ConfigDict, Field, RootModel

# ---------- API HTTP ----------


class TemaIn(BaseModel):
    texto: str
    plantilla: str = "curiosidades"


class EstadoIdeaIn(BaseModel):
    estado: str  # propuesta | aprobada | descartada


class GuionIn(BaseModel):
    gancho: str
    frases: list[str]
    cta: str


# ---------- Salidas de los LLMs ----------
# Cada modelo cumple doble función: genera el JSON schema que restringe la
# generación en llama-server, y valida/parsea la respuesta al volver.


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


# ---------- Plantillas (plantillas/<nombre>/plantilla.json) ----------


class VozPlantilla(BaseModel):
    instruct: str
    language: str


class SubtitulosPlantilla(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_palabras_por_bloque: int = Field(default=3, ge=1, le=8)


class RitmoPlantilla(BaseModel):
    model_config = ConfigDict(extra="allow")
    duracion_objetivo_s: int = Field(ge=15, le=120)
    duracion_escena_s: float = Field(default=4, gt=0)
    atempo: float = Field(default=1.0, ge=0.5, le=2.0)


class Plantilla(BaseModel):
    model_config = ConfigDict(extra="allow")
    nombre: str
    descripcion: str = ""
    voz: VozPlantilla
    estilo_visual: str
    subtitulos: SubtitulosPlantilla
    ritmo: RitmoPlantilla
