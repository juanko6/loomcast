from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc

ORDEN_ESTADOS = [
    "IDEA", "GUION", "METADATOS", "VOZ", "SUBTITULOS", "ESCENAS",
    "IMAGENES", "UPSCALE", "CLIPS", "INTERPOLADO", "FINAL",
]


class Proyecto(Base):
    __tablename__ = "proyectos"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"))
    slug: Mapped[str] = mapped_column(unique=True)
    plantilla: Mapped[str] = mapped_column(default="curiosidades")
    # Slug de la voz del banco elegida para narrar este proyecto
    voz: Mapped[str | None] = mapped_column(default=None)
    # Pista de música de este proyecto (fila de `musicas`). Vive en la
    # biblioteca de Música como cualquier otra pista, para poder escucharla y
    # descargarla sola, sin la narración: es el audio reutilizable en redes.
    # None = el proyecto no tiene música.
    musica_id: Mapped[int | None] = mapped_column(
        ForeignKey("musicas.id"), default=None
    )
    # Si el armado mezcla esa pista por debajo de la voz (con ducking). Tener
    # música y mezclarla son decisiones distintas: lo normal es querer la pista
    # aparte, y el vídeo con música es opcional.
    musica_mezclar: Mapped[bool] = mapped_column(default=False)
    # Serie de la que este proyecto es un episodio. None = vídeo suelto, que es
    # lo que son todos los de antes de la Fase 8 y lo que sigue siendo cualquier
    # proyecto creado desde un tema sin serie: sin estas tres columnas puestas,
    # el pipeline hace exactamente lo de siempre.
    serie_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id"), default=None
    )
    # Número de episodio dentro de la serie (1, 2, 3…). 0 = no es un episodio.
    # Es el que se estampa en el vídeo y el que ordena la continuidad; no se
    # recalcula al borrar un episodio del medio, porque el episodio 4 ya se
    # publicó llamándose 4.
    episodio: Mapped[int] = mapped_column(default=0)
    # Qué pasó en este episodio, para que el siguiente lo sepa. Lo escribe el
    # LLM al cerrarlo y es editable como el resto de los textos del proyecto: la
    # continuidad de una serie no puede depender de un resumen que nadie puede
    # corregir. Vacío = sin cerrar todavía (o proyecto suelto).
    resumen_episodio: Mapped[str] = mapped_column(Text, default="")
    # De qué versión del guion salió ese resumen. El resumen se escribe al
    # aprobar el guion y no al armar el vídeo, porque la historia queda cerrada
    # cuando está escrita: ni la voz ni las imágenes ni el i2v añaden un hecho.
    # Eso permite escribir la temporada entera antes de producir nada, y obliga
    # a llevar la cuenta: si el guion se edita y pasa a la v2, el resumen de la
    # v1 miente, y lo que miente aquí se vuelve canon en el capítulo siguiente.
    # 0 = sin resumen todavía (o proyecto suelto).
    resumen_version: Mapped[int] = mapped_column(default=0)
    # Qué se salió del tramo que el hilo le había asignado, si se salió. Lo
    # escribe el LLM junto con el resumen, que es cuando tiene delante el guion
    # y el plan a la vez. Vacío con resumen escrito = cumplió su tramo (o la
    # serie no tiene hilo); es el detector de deriva, y no una cuarta columna
    # con un "sí/no" que habría que mantener de acuerdo con esta.
    tramo_desvio: Mapped[str] = mapped_column(Text, default="")
    # Un episodio anterior se reescribió DESPUÉS de que este se escribiera, así
    # que este salió de un canon que ya no es el que hay. No se regenera solo a
    # propósito: regenerar en cascada tiraría guiones ya aprobados, y lo hecho
    # no se toca (el mismo criterio que el reparto fijo y el hilo). Se marca, y
    # decide el usuario.
    continuidad_rota: Mapped[bool] = mapped_column(default=False)
    # Cuándo se subió el vídeo y dónde quedó. Es la única parte del proyecto
    # que habla de fuera de esta máquina: lo de aquí se puede rehacer, un vídeo
    # ya publicado no. Cadena vacía = sin publicar, que es lo que son todos los
    # de antes de esta columna; la fecha la pone quien lo marca (ISO corta,
    # "2026-10-29"), porque subir y marcar no pasan a la vez.
    publicado_en: Mapped[str] = mapped_column(default="")
    # Enlace o id del vídeo en YouTube, tal y como se pegó.
    publicado_url: Mapped[str] = mapped_column(default="")
    publicado_nota: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(default="IDEA")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


def avanzar_estado(proyecto: Proyecto, nuevo: str) -> None:
    """El estado solo avanza (re-ejecutar una etapa no lo retrocede)."""
    if ORDEN_ESTADOS.index(nuevo) > ORDEN_ESTADOS.index(proyecto.estado):
        proyecto.estado = nuevo
