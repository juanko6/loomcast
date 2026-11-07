"""Contrato de plantillas/<nombre>/plantilla.json (validado al cargar)."""
from pydantic import BaseModel, ConfigDict, Field


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
    # "frases": guion como {gancho, frases[], cta} (por defecto).
    # "narracion": guion como {narracion} — un párrafo hablado continuo que el
    # TTS lee de corrido, para storytelling sin cadencia de lista leída.
    # "lineas": guion como {lineas[]} — narración con líneas atribuidas a un
    # personaje del reparto, que las dice con su propia voz. Ninguna plantilla
    # lo usa todavía: la capacidad está para las series (Fase 8).
    formato_guion: str = Field(
        default="frases", pattern="^(frases|narracion|lineas)$"
    )
    # Con qué se llena `clips/`. "imagen": el camino de siempre — una imagen
    # generada por escena, reescalada y animada (estático, Ken Burns o i2v).
    # "motion": nada de imágenes; cada escena es una composición dibujada por
    # código sobre una simulación (ver pipeline/motion.py). No son
    # intercambiables, porque lo que el LLM escribe por escena es distinto: un
    # prompt visual en un caso y una ficha de composición en el otro. Por eso
    # lo declara la plantilla y no se elige al generar el vídeo.
    montaje: str = Field(default="imagen", pattern="^(imagen|motion)$")
