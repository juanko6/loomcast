from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Serie(Base):
    """Un hilo de episodios: lo que mejor funciona en Shorts.

    Un proyecto suelto cuenta algo y se acaba. Una serie cuenta lo mismo que
    cuentan diez proyectos seguidos, pero con lo que hace que el espectador
    vuelva: la misma gente y una historia que avanza. La continuidad sale de dos
    sitios, y los dos estaban ya construidos:

    - **El reparto fijo** (`SerieMiembro` → reparto propio): cada episodio nuevo
      se trae a los mismos personajes con su ficha, su cara y su voz ya
      fijadas, sin volver a describirlos. Para esto se hizo el reparto
      persistente.
    - **El resumen del episodio anterior** (`Proyecto.resumen_episodio`), que
      entra como contexto al escribir el guion del siguiente.

    La serie **no tiene estado de producción**: el ciclo
    `IDEA → … → FINAL` es de cada episodio y se queda ahí. Mezclar el progreso
    de la serie con el del proyecto obligaría a decidir qué significa una serie
    "en VOZ" con tres episodios en puntos distintos, y no significa nada.
    """

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Identificador estable para la URL, como en el banco de voces y el reparto.
    slug: Mapped[str] = mapped_column(unique=True)
    nombre: Mapped[str] = mapped_column()
    # La plantilla de la serie manda sobre la de sus episodios: es la que decide
    # el nicho, el formato de guion (la de `serie` activa las líneas atribuidas)
    # y los ocho prompts. No se elige por episodio a propósito: una serie en la
    # que cada capítulo suena a otro programa no es una serie.
    plantilla: Mapped[str] = mapped_column(default="serie")
    # Tema del que cuelgan las ideas de episodio. Las ideas necesitan un tema
    # (es su dueño en la base), y tenerlo propio da gratis el "pedir más ideas"
    # de siempre, solo que con el prompt de ideas de la plantilla de serie, que
    # piensa en episodios y no en vídeos sueltos. Aprobar una de esas ideas crea
    # el episodio siguiente.
    tema_id: Mapped[int] = mapped_column(ForeignKey("temas.id"))
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


class SerieMiembro(Base):
    """Alguien del reparto propio que sale en todos los episodios de una serie.

    Guarda el `slug` del miembro y no una copia de su ficha: aquí no hay nada
    que se pegue en un prompt, es la lista de a quién traer. La copia —ficha,
    cara, voz— la hace `services/reparto.traer` al entrar en cada episodio, que
    es donde tiene sentido que el proyecto se quede con lo suyo.
    """

    __tablename__ = "serie_miembros"

    id: Mapped[int] = mapped_column(primary_key=True)
    serie_id: Mapped[int] = mapped_column(ForeignKey("series.id"))
    # Slug del miembro en `reparto`. Borrarlo de allí borra también estas filas
    # (ver repositories/series.desvincular_reparto): si no, cada episodio nuevo
    # intentaría traer a alguien que ya no existe.
    reparto_slug: Mapped[str] = mapped_column()
    # Orden en el que se traen al episodio, para que las claves se repartan
    # igual en todos (el primero se queda {ANA}, el segundo {ANA_2} si choca).
    orden: Mapped[int] = mapped_column(default=0)
