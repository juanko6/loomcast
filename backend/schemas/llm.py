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
    # Instrucción de voz (4 bloques) adaptada a esta historia; la usa el modo de
    # narración "design" (VoiceDesign) para que la entrega encaje con el relato.
    voz_instruct: str = Field(min_length=1)


class GuionNarracionLLM(BaseModel):
    """Guion de narración continua (plantillas con formato_guion="narracion").

    El cuerpo es un único párrafo hablado que el TTS lee de corrido —sin la
    cadencia de lista leída de las frases sueltas—, pero el gancho de apertura
    y el cta de cierre se mantienen como campos propios: garantizados por
    esquema y editables aparte. Al narrar se unen gancho + narracion + cta.
    """
    gancho: str = Field(min_length=1)
    narracion: str = Field(min_length=1)
    cta: str = Field(min_length=1)
    # Instrucción de voz (4 bloques) adaptada a esta historia; la usa el modo de
    # narración "design" (VoiceDesign) para que la entrega encaje con el relato.
    voz_instruct: str = Field(min_length=1)


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


class ImagenLibrePromptLLM(BaseModel):
    # Prompt final en inglés, para la galería de imágenes (generar o editar).
    prompt: str = Field(min_length=20)


class MusicaPromptLLM(BaseModel):
    # Descripción de estilo para ACE-Step 1.5 (inglés, en prosa): género,
    # instrumentación, rol de cada elemento en la mezcla, producción y cómo
    # evoluciona el arreglo. Se llama `tags` porque así se llama la entrada del
    # nodo, pero 1.5 no espera etiquetas coma-separadas sino un párrafo.
    tags: str = Field(min_length=20)
    # Letra con marcadores [Verse 1 - ...] / [Chorus - ...]; cadena vacía para
    # pistas instrumentales.
    lyrics: str = ""
    # Conditioning musical. Los cuatro se normalizan contra los combos del nodo
    # en services/musica_combos.py, así que aquí basta con tipos laxos.
    bpm: int = 120
    # "<raíz> <major|minor>", p. ej. "E minor".
    keyscale: str = "C major"
    # "2" | "3" | "4" | "6".
    timesig: str = "4"
    # Código corto del idioma de la letra: "es", "en"…
    idioma: str = "es"
