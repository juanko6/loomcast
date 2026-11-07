"""Contratos de salida de los LLMs.

Cada modelo cumple doble función: genera el JSON schema que restringe la
generación en llama-server, y valida/parsea la respuesta al volver.
"""
import difflib

from pydantic import BaseModel, Field, RootModel, model_validator


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


class LineaGuionLLM(BaseModel):
    """Un tramo del cuerpo del guion: quién lo dice y qué dice."""

    # Clave del personaje que la dice ({ANA} en los prompts de escena), o cadena
    # vacía para el narrador. No se valida contra el reparto aquí: el casting es
    # posterior al guion, así que la clave que escribe el LLM al escribir la
    # historia es justo la que el casting encontrará luego en el texto.
    personaje: str = ""
    texto: str = Field(min_length=1)


class GuionLineasLLM(BaseModel):
    """Guion con líneas atribuidas (plantillas con formato_guion="lineas").

    El narrador sigue llevando la historia y los personajes dicen líneas
    puntuales: no es un diálogo por turnos. El cuerpo es la lista de tramos en
    orden, cada uno con su dueño; el gancho y el cta siguen siendo campos
    propios y los dice el narrador, como en los otros dos formatos.
    """
    gancho: str = Field(min_length=1)
    lineas: list[LineaGuionLLM] = Field(min_length=1)
    cta: str = Field(min_length=1)
    # Instrucción de voz (4 bloques) adaptada a esta historia; la usa el modo de
    # narración "design" (VoiceDesign) para que la entrega encaje con el relato.
    voz_instruct: str = Field(min_length=1)


class PersonajeLLM(BaseModel):
    # Token con el que las escenas lo referencian: {ANA}. Se normaliza a
    # mayúsculas al guardarlo, así que aquí basta con exigir que venga algo.
    clave: str = Field(min_length=1, max_length=24)
    nombre: str = Field(min_length=1, max_length=60)
    # "persona" o "objeto". El reparto admite las dos cosas a propósito (un
    # barco o un mapa que vuelve en varias escenas también tiene que no mutar),
    # pero su retrato de referencia se encuadra distinto: pedirle cara, pelo y
    # piel a un mapa le pinta una cara encima. Por defecto persona, que es el
    # caso común; el valor se normaliza en casting.py.
    tipo: str = "persona"
    # Descripción física en inglés, concreta y visual. Es lo que se sustituye
    # palabra por palabra en cada prompt donde salga el personaje.
    ficha: str = Field(min_length=20)


class TramoLLM(BaseModel):
    """El sitio que ocupa un episodio en el hilo de la serie."""

    # Se renumera por posición al guardar (repositories/hilos.normalizar): el
    # número de un tramo es el episodio al que le toca, no un dato que el LLM
    # pueda equivocar. Va en el esquema para que el modelo piense en orden.
    numero: int = 0
    titulo: str = Field(min_length=1, max_length=120)
    # Qué pasa en ese episodio.
    pasa: str = Field(min_length=1)
    # Qué ha cambiado al terminarlo, y que ya no se puede deshacer. Un tramo sin
    # esto es relleno, y el prompt lo pide así por eso.
    cambia: str = Field(min_length=1)


class HiloLLM(BaseModel):
    """Hacia dónde va la serie: lo que el LLM escribe desde la premisa.

    `episodios_recomendados` es una recomendación de verdad: el número lo decide
    el usuario y solo manda esta cuando no lo ha decidido. Cuántos episodios
    tiene la serie se lee de `len(tramos)`, que es el mapa que se va a usar.
    """

    premisa: str = Field(min_length=1)
    pregunta: str = Field(min_length=1)
    destino: str = Field(min_length=1)
    # Los protagonistas, con la misma forma que los del casting de un episodio
    # (`PersonajeLLM`): es el mismo trabajo hecho antes, y la ficha acaba en los
    # mismos sitios. Salen del hilo porque en una serie el reparto no es de un
    # capítulo: se ficha una vez, se le hace cara y voz, y vuelve en todos.
    # No se guarda en el hilo (ver `pipeline/series.generar_hilo`): se convierte
    # en reparto fijo de la serie, que es donde vive el reparto de verdad.
    reparto: list[PersonajeLLM] = Field(min_length=1, max_length=5)
    # Lo que esta serie NO es. Lista a propósito: son vetos que se leen de un
    # vistazo y se tachan de uno en uno al editar el hilo.
    fuera: list[str] = Field(min_length=1, max_length=10)
    episodios_recomendados: int = Field(ge=2, le=24)
    por_que: str = Field(min_length=1)
    # Uno por episodio. El mínimo es 1 y no 2 porque al replanificar una serie
    # a medias esto es solo la cola que falta, y puede quedar un capítulo.
    tramos: list[TramoLLM] = Field(min_length=1, max_length=24)


class ResumenEpisodioLLM(BaseModel):
    """En qué quedó un episodio, para que el siguiente lo sepa.

    El resumen es un solo campo a propósito: es un texto que el usuario va a
    leer y corregir antes de que entre en el guion del capítulo que viene, y
    partirlo en "qué pasó" y "qué queda abierto" obligaría a editar dos cajas
    para arreglar una misma frase. Lo que tiene que llevar lo dicta el prompt.

    `tramo_desvio` no es un trozo del resumen, es otra cosa: el resumen cuenta
    los hechos, y el desvío es un juicio sobre el plan. Se piden juntos porque
    este es el único momento en el que el LLM tiene delante el guion y el tramo
    del hilo a la vez.
    """

    resumen: str = Field(min_length=40, max_length=1200)
    # Qué hizo este episodio que no era lo que su tramo decía, en una frase.
    # Cadena vacía = cumplió (o la serie no tiene hilo y no había nada que
    # cumplir): el prompt pide explícitamente no inventarse un desvío.
    tramo_desvio: str = ""


class TituloLLM(BaseModel):
    # El prompt pide 35-55 chars (máx 65); el margen evita rechazar por poco
    titulo: str = Field(min_length=10, max_length=80)


class DescripcionLLM(BaseModel):
    # El prompt pide 250-450 chars; margen amplio para no rechazar por poco
    descripcion: str = Field(min_length=100, max_length=600)


class EtiquetasLLM(BaseModel):
    etiquetas: list[str] = Field(min_length=5, max_length=15)
    tiktok: str = Field(min_length=1, max_length=250)


class CastingLLM(BaseModel):
    # Lista vacía cuando el guion no tiene nada recurrente (frecuente en
    # curiosidades): no hay nada que fijar y las escenas van como siempre.
    personajes: list[PersonajeLLM] = []


class PlanoLLM(BaseModel):
    # Tamaño de plano y ángulo ("wide establishing shot, high angle").
    camara: str = Field(min_length=1)
    # Qué pasa en el plano, en inglés y con los marcadores {CLAVE} del reparto.
    accion: str = Field(min_length=1)


class StoryboardLLM(BaseModel):
    # El mundo visual del video entero: época, lugares, hora, atrezo, luz.
    mundo: str = Field(min_length=1)
    # Un plano por segmento de voz, en orden. El largo lo cuadra escenas.py:
    # no se puede fijar en el esquema porque cambia con cada video.
    planos: list[PlanoLLM] = Field(min_length=1)


class EscenaLLM(BaseModel):
    prompt: str = Field(min_length=20)
    # Qué se mueve en la escena; solo lo usa el modo i2v
    prompt_movimiento: str = Field(min_length=20)


class ImagenLibrePromptLLM(BaseModel):
    # Prompt final en inglés, para la galería de imágenes (generar o editar).
    prompt: str = Field(min_length=20)


class AnimadaMovimientoLLM(BaseModel):
    # Prompt de movimiento pulido (inglés) para el bucle de una imagen animada,
    # y la duración que el LLM recomienda para él.
    prompt: str = Field(min_length=20)
    duracion_s: int = Field(ge=10, le=15)


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
    # Prompt en inglés para la portada de la pista (imagen cuadrada). Se genera
    # con el motor de imagen en un job encadenado.
    portada: str = ""

    @model_validator(mode="before")
    @classmethod
    def _claves_mal_escritas(cls, datos):
        """Recoloca las claves que el modelo escribe con una errata.

        El Qwen 35B en 4 bits devuelve `"lytics"` en vez de `"lyrics"`, y como
        mlx_lm ignora el json_schema nadie lo frena: Pydantic descarta la clave
        desconocida, `lyrics` se queda en "" y el guion de secciones se pierde
        sin ningún aviso (pasó en todas las pistas desde la 33). Una clave que
        no existe y se parece mucho a un campo que falta es ese campo.
        """
        if not isinstance(datos, dict):
            return datos
        faltan = [c for c in cls.model_fields if c not in datos]
        for clave in [k for k in datos if k not in cls.model_fields]:
            parecida = difflib.get_close_matches(clave, faltan, n=1, cutoff=0.8)
            if parecida:
                datos[parecida[0]] = datos.pop(clave)
                faltan.remove(parecida[0])
        return datos
