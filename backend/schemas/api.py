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


class VozGenerarIn(BaseModel):
    # "clon": clona la voz del banco (Base). "design": narra con VoiceDesign
    # usando el instruct de la plantilla (experimental, más expresivo).
    modo: str = "clon"
    # Instruct a medida para el modo "design" (editable desde la UI). Si viene,
    # se usa tal cual y NO se lee de la plantilla (así la caché no estorba); si
    # es None, se cae al voz.instruct de la plantilla.
    instruct: str | None = None


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


class GaleriaGenerarIn(BaseModel):
    idea: str
    width: int = 768
    height: int = 1344
    # Id de [imagen.motores] de config.toml; None = el motor por defecto.
    motor: str | None = None


class GaleriaPromptIn(BaseModel):
    prompt: str


class GaleriaPreviewsIn(BaseModel):
    # Opcional: reajustar el tamaño antes de lanzar las previews. Si son None se
    # usa el guardado al crear la entrada.
    width: int | None = None
    height: int | None = None


class GaleriaFinalIn(BaseModel):
    indice: int


class MusicaGenerarIn(BaseModel):
    # instrumental (música de fondo / jingle, sin voz) | cancion (con letra)
    tipo: str = "instrumental"
    idea: str = ""
    # Opcionales: si el usuario ya escribió la descripción/letra a mano, se
    # guardan al crear; si no, se rellenan luego con "mejorar" (LLM).
    tags: str = ""
    lyrics: str = ""
    duracion_s: int = 30
    # Conditioning musical de ACE-Step 1.5. None = valor por defecto del
    # servicio; se normaliza contra los combos del nodo antes de guardar.
    bpm: int | None = None
    keyscale: str | None = None
    timesig: str | None = None
    idioma: str | None = None


class MusicaCamposIn(BaseModel):
    # Edición de los campos antes de generar (None = no tocar).
    tags: str | None = None
    lyrics: str | None = None
    duracion_s: int | None = None
    bpm: int | None = None
    keyscale: str | None = None
    timesig: str | None = None
    idioma: str | None = None


class MusicaLanzarIn(BaseModel):
    # Campos con los que generar (se persisten antes de encolar). Si vienen
    # vacíos se usan los ya guardados. seed None = aleatorio.
    tags: str | None = None
    lyrics: str | None = None
    duracion_s: int | None = None
    seed: int | None = None
    bpm: int | None = None
    keyscale: str | None = None
    timesig: str | None = None
    idioma: str | None = None
