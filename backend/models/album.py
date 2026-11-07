from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Album(Base):
    """Un álbum: varias pistas con el mismo sonido y distinta intención.

    Lo constante vive aquí (el ADN): el género, la banda y la firma de
    producción, que se pega literal al final del brief de cada pista para que
    todas compartan color sonoro sin depender de que el LLM lo recuerde. Lo que
    cambia vive en cada `Musica` del álbum: su intención, su forma, su tempo y
    tonalidad, y su duración, que sale de los compases de su guion.

    **La variación no es la semilla.** Todas las pistas se sintetizan con la
    misma (`seed`): así lo único que distingue una pista de otra es lo que
    pretende contar.

    Ciclo de vida:
      - `planificando`: el LLM escribe el ADN, el tracklist y el brief de cada
        pista (jobs `planificar_album` → `escribir_album`).
      - `revision`: todo escrito; el usuario lo revisa y edita antes de gastar
        GPU.
      - `produciendo`: lanzado. Que esté terminado se deduce de sus pistas.
    """

    __tablename__ = "albumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(default="")
    # Lo que escribió el usuario, o vacío si el álbum sale de una pista.
    idea: Mapped[str] = mapped_column(Text, default="")
    # Pista de la que sale el ADN, o None si sale de una idea. No es FK: si se
    # borra, el álbum sigue teniendo sentido.
    origen_musica_id: Mapped[int | None] = mapped_column(default=None)
    # Cuántas pistas pidió el usuario, contando la de origen.
    num_pistas: Mapped[int] = mapped_column(default=12)
    # ADN en texto llano: género, banda (una por línea en `banda`) y la firma
    # de producción que se pega literal en cada brief.
    genero: Mapped[str] = mapped_column(Text, default="")
    banda: Mapped[str] = mapped_column(Text, default="")
    firma: Mapped[str] = mapped_column(Text, default="")
    # Arco del álbum en una frase o dos: cómo abre, dónde sube, cómo cierra.
    arco: Mapped[str] = mapped_column(Text, default="")
    # Semilla común a todas las pistas.
    seed: Mapped[int] = mapped_column(default=0)
    # Prompt en inglés de la portada del álbum (una sola para todo el disco).
    portada: Mapped[str | None] = mapped_column(Text, default=None)
    # planificando | revision | produciendo
    estado: Mapped[str] = mapped_column(default="planificando")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
