"""Contratos de la API HTTP (entrada de los routers)."""
from pydantic import BaseModel, Field


class TemaIn(BaseModel):
    texto: str
    plantilla: str = "curiosidades"


class ParadaIn(BaseModel):
    """Qué se para. Separados porque no es lo mismo tirar los minutos de GPU de
    la etapa en curso que vaciar lo que todavía no ha empezado."""

    corriendo: bool = True
    pendientes: bool = True


class EstadoIdeaIn(BaseModel):
    estado: str  # propuesta | aprobada | descartada


class LineaGuionIn(BaseModel):
    # Clave del personaje que la dice; vacío = narrador. Se normaliza en el
    # servicio, igual que al escribirla el LLM.
    personaje: str = ""
    texto: str = ""


class GuionIn(BaseModel):
    # Tres formas según la plantilla: {gancho, frases[], cta}, {narracion} o
    # {lineas[]}. Todos opcionales para que la edición admita cualquiera.
    gancho: str = ""
    frases: list[str] = []
    cta: str = ""
    narracion: str = ""
    lineas: list[LineaGuionIn] = []


class SerieIn(BaseModel):
    """Una serie nueva: nombre, plantilla, premisa y cuántos episodios.

    La plantilla no se pide por episodio a propósito (ver models/serie.py): es
    la que decide el nicho, el formato de guion y los ocho prompts de todos.

    La premisa es opcional pero es de donde sale el hilo, o sea el sitio que
    ocupa cada capítulo. Sin ella la serie nace solo con continuidad hacia
    atrás, y el hilo se puede pedir después.
    """
    nombre: str = Field(min_length=1, max_length=120)
    plantilla: str = "serie"
    premisa: str = Field(default="", max_length=2000)
    # Cuántos episodios quiere el usuario. 0 = que lo decida el LLM, que además
    # dirá por qué ese número: es la respuesta normal.
    episodios: int = Field(default=0, ge=0, le=24)


class SerieAjusteIn(BaseModel):
    """La premisa y el número de episodios de una serie que ya existe.

    Guardarlos no reescribe el hilo: rehacerlo es otro botón, porque en una
    serie a medias eso replanifica los capítulos que no se han escrito.
    """
    premisa: str = Field(default="", max_length=2000)
    episodios: int = Field(default=0, ge=0, le=24)


class TramoIn(BaseModel):
    # Un tramo corregido a mano. Vaciarlo es como se borra (lo tira
    # `repositories/hilos.normalizar`, que además renumera).
    titulo: str = ""
    pasa: str = ""
    cambia: str = ""


class HiloIn(BaseModel):
    """El hilo corregido a mano. Todo opcional, como en la edición del guion.

    El `numero` de cada tramo no se acepta a propósito: es su posición en la
    lista, y dejar que lo mande el editor es dejar que un episodio se quede sin
    tramo o con el de otro.
    """
    premisa: str = ""
    pregunta: str = ""
    destino: str = ""
    fuera: list[str] = []
    episodios_recomendados: int = 0
    por_que: str = ""
    tramos: list[TramoIn] = []


class SerieMiembroIn(BaseModel):
    # Slug de alguien del reparto propio, que pasa a salir en todos los
    # episodios siguientes.
    reparto_slug: str = Field(min_length=1)


class EpisodioNuevoIn(BaseModel):
    """Opcional: una línea de dirección para el episodio.

    Vacío = lo propone el LLM desde el resumen del episodio anterior, que es
    para lo que se escribe ese resumen.
    """
    apunte: str = ""


class ResumenEpisodioIn(BaseModel):
    # En qué quedó el episodio, corregido a mano. Es lo que el guion del
    # siguiente dará por cierto.
    resumen: str = ""


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


class VozPersonajeIn(BaseModel):
    """Qué voz del banco dice las líneas de un personaje del reparto.

    Cadena vacía = se queda sin voz propia y sus líneas las narra la voz del
    proyecto, que es el comportamiento de siempre.
    """
    voz: str = ""


class MusicaProyectoIn(BaseModel):
    """Qué pista usa el proyecto y si el armado la mezcla.

    `musica_id` None desengancha la pista (la fila sigue en la biblioteca de
    Música: es reutilizable y no se borra con el proyecto).
    """
    musica_id: int | None = None
    mezclar: bool = False


class EscenaPromptIn(BaseModel):
    orden: int
    prompt: str
    # Opcional: si no viene, se conserva el que ya tuviera la escena
    prompt_movimiento: str | None = None


class EscenasIn(BaseModel):
    escenas: list[EscenaPromptIn]


class PersonajeIn(BaseModel):
    # La clave identifica al personaje y no se edita: es el marcador con el que
    # ya están escritos los prompts de escena.
    clave: str
    nombre: str
    ficha: str


class PersonajesIn(BaseModel):
    personajes: list[PersonajeIn]


class PersonajeNuevoIn(BaseModel):
    # La clave se normaliza en el servicio (mayúsculas, sin espacios); aquí solo
    # se exige que venga algo.
    clave: str = Field(min_length=1, max_length=24)
    nombre: str = ""
    ficha: str = ""


class RepartoDesdeProyectoIn(BaseModel):
    """Qué personaje de qué proyecto se guarda en el reparto propio.

    El alta no es un formulario en blanco: se promueve a alguien que ya tiene
    ficha y retrato buenos, que es cuando uno sabe que quiere conservarlo.
    `nombre` vacío = se usa el que tenga en el proyecto.
    """
    proyecto_id: int
    clave: str = Field(min_length=1, max_length=24)
    nombre: str = ""


class RepartoTraerIn(BaseModel):
    proyecto_id: int


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
    modo: str = "kenburns"  # estatico | kenburns | i2v | mixto
    # Motor i2v ([i2v.motores] de config.toml). Vacío = el de [i2v].motor. Solo
    # lo miran los modos que generan i2v.
    motor: str = ""


class PublicacionIn(BaseModel):
    """Que este vídeo ya está subido. La fecha va aparte del momento de marcar
    porque se sube un día y se apunta otro; vacía = hoy."""

    fecha: str = ""
    # Enlace o id del vídeo, tal y como se pegue.
    url: str = ""
    nota: str = ""


class AutopilotoIn(BaseModel):
    """Con qué se lanza una tirada automática.

    El modo de montaje y con qué se narra se piden aquí porque son las dos
    decisiones que el flujo a mano también pide (el paso de vídeo y el paso de
    voz) y ninguna tiene un valor obvio: la voz, además, es lo primero con lo
    que se tropezaría la narración si faltara.

    `paradas` None = las de [autopiloto] de config.toml, que son las tres de
    siempre. Una lista vacía es producción sin manos, y por eso no se puede
    confundir con "no dijo nada".
    """
    modo: str = "kenburns"  # estatico | kenburns | i2v | mixto
    # Motor i2v ([i2v.motores] de config.toml). Vacío = el de [i2v].motor.
    motor: str = ""
    # Con qué se narra, igual que en el paso de voz: "clon" clona la voz del
    # banco de `voz`, y "design" es la narración expresiva, que la escribe
    # VoiceDesign con el estilo que el LLM saca de cada historia (y entonces
    # `voz` no hace falta: en un lote de historias distintas es lo que evita que
    # una voz elegida a mano narre todas las demás).
    narracion: str = "clon"
    # Slug de la voz del banco con la que narrar. Vacío = la que ya tenga el
    # proyecto elegida.
    voz: str = ""
    # idea | guion | escenas
    paradas: list[str] | None = None


class LoteIn(AutopilotoIn):
    """Un lote: las ideas de un tema produciéndose una detrás de otra."""
    tema_id: int


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
