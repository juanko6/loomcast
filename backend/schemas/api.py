"""Contratos de la API HTTP (entrada de los routers)."""
from pydantic import BaseModel


class TemaIn(BaseModel):
    texto: str
    plantilla: str = "curiosidades"


class EstadoIdeaIn(BaseModel):
    estado: str  # propuesta | aprobada | descartada


class GuionIn(BaseModel):
    # Dos formas según la plantilla: {gancho, frases[], cta} o {narracion}.
    # Todos opcionales para que la edición admita cualquiera de las dos.
    gancho: str = ""
    frases: list[str] = []
    cta: str = ""
    narracion: str = ""


class VozNuevaIn(BaseModel):
    nombre: str
    instruct: str


class VozSeleccionIn(BaseModel):
    voz: str  # slug de la voz del banco


class EscenaPromptIn(BaseModel):
    orden: int
    prompt: str
    # Opcional: si no viene, se conserva el que ya tuviera la escena
    prompt_movimiento: str | None = None


class EscenasIn(BaseModel):
    escenas: list[EscenaPromptIn]


class RegenerarImagenIn(BaseModel):
    # True = otra imagen distinta; False = mismo seed, solo cambia si se editó
    # el prompt.
    nuevo_seed: bool = True


class RegenerarClipIn(BaseModel):
    # estatico | kenburns | i2v. Vacío = el modo guardado en la escena.
    modo: str = ""


class ModoEscenaIn(BaseModel):
    orden: int
    modo: str


class ModosEscenasIn(BaseModel):
    escenas: list[ModoEscenaIn]


class VideoIn(BaseModel):
    modo: str = "kenburns"  # estatico | kenburns
