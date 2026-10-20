from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class MiembroReparto(Base):
    """Alguien del reparto propio: una ficha y una cara que sobreviven al vídeo.

    El `Personaje` de un proyecto muere con él (cuelga de `proyecto_id`), así que
    un narrador que vuelve en diez vídeos había que describirlo y retratarlo diez
    veces, y salía distinto cada vez. Esta tabla es el reparto de la casa: se
    guarda una vez y se trae a cualquier proyecto nuevo con la ficha y la cara ya
    fijadas, que es justo lo que evita la deriva entre vídeos (el mismo problema
    que la ficha resuelve entre escenas, un nivel más arriba).

    Al traerlo a un proyecto **su retrato se copia**, no se referencia: los
    proyectos son autocontenidos en disco, y borrar de aquí no puede romper un
    vídeo ya hecho ni cambiar uno antiguo por detrás.
    """

    __tablename__ = "reparto"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Identificador en la URL y nombre de su carpeta, como en el banco de voces.
    slug: Mapped[str] = mapped_column(unique=True)
    # Cómo lo llama el usuario en el listado ("Ana, la narradora"). Es lo único
    # que distingue a dos miembros parecidos, así que no se deriva de la clave.
    nombre: Mapped[str] = mapped_column()
    # Marcador con el que se le nombrará en los prompts del proyecto al que se
    # traiga ({ANA}). Es una propuesta, no una reserva: si en ese proyecto ya hay
    # alguien con esa clave, se le da otra al traerlo (ver services/reparto.py).
    clave: Mapped[str] = mapped_column()
    # Descripción física en inglés, igual que la del personaje de proyecto: se
    # sustituye literal en cada prompt donde sale.
    ficha: Mapped[str] = mapped_column(Text, default="")
    # persona | objeto. Viaja con el miembro: un barco recurrente también es
    # reparto, y su retrato se encuadra sin pedirle cara.
    tipo: Mapped[str] = mapped_column(default="persona")
    # Semilla del retrato guardado. Viaja para que rehacerle la cara en un
    # proyecto nuevo "con el mismo seed" dé la misma persona que ya tenía.
    seed: Mapped[int] = mapped_column(default=0)
    # Slug de su voz en el banco. Viaja con él igual que la ficha y la cara: un
    # narrador recurrente que ya sonaba bien no tiene por qué volver a sonar
    # distinto en el vídeo siguiente. A diferencia del retrato **no se copia**,
    # porque una voz del banco ya es un recurso compartido entre proyectos y
    # duplicar su `ref.wav` por vídeo serían megas por nada; si la voz se borra
    # del banco, el miembro se queda sin ella (ver desvincular_voz).
    voz: Mapped[str] = mapped_column(default="")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
