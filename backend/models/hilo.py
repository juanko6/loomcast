from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Hilo(Base):
    """Hacia dónde va una serie: el plan que los episodios no pueden desmentir.

    La continuidad que ya había mira **atrás**: el reparto fijo y el resumen del
    episodio anterior impiden contradecir lo que pasó. Pero nada apuntaba hacia
    delante, y sin destino cada capítulo está obligado a abrir algo nuevo —el
    prompt de ideas pide no cerrar la serie y el de guion no resolverla—, así que
    abrir algo nuevo diez veces *es* la deriva. El hilo es la mitad que faltaba:
    dice de qué va la serie, cómo acaba y por qué sitios pasa.

    Se guarda como el guion y por lo mismo: **JSON versionado y editable**. Lo
    escribe el LLM desde la premisa al crear la serie, pero es un plan, y un plan
    que nadie puede corregir deriva igual que un resumen que nadie puede
    corregir. Cada versión se queda: replanificar lo que falta no borra lo que se
    decidió al empezar.

    Qué lleva el `contenido`:

    - `premisa`, `pregunta` (la que el espectador quiere ver respondida),
      `destino` (cómo acaba, y esto es lo que antes no existía en ningún sitio).
    - `fuera`: lo que esta serie **no** es. Un "fuera de hilo" explícito frena la
      deriva mejor que diez reglas de estilo, porque la deriva no suele ser un
      error de tono: es un capítulo que se va a otro género.
    - `tramos`: uno por episodio, en orden. Son el mapa, y son lo que convierte
      el hilo en algo con lo que se puede trabajar: el episodio 4 sabe que es el
      4 de 6, y el 6 sabe que cierra. De ahí sale el único prompt que hoy es
      imposible de pedir, el del capítulo final.
    - `episodios_recomendados` y `por_que`: cuántos aguanta la premisa, en
      opinión del LLM. Es una recomendación porque el número lo decide el
      usuario; cuando no lo decide, manda esta.

    **Cuántos episodios tiene la serie es `len(tramos)`**, no un campo aparte:
    `Serie.episodios_objetivo` es lo que se *pidió* (0 = "decide tú"), y el mapa
    es lo que hay. Dos sitios donde leer el mismo número es un sitio donde no
    van a coincidir.
    """

    __tablename__ = "hilos"

    id: Mapped[int] = mapped_column(primary_key=True)
    serie_id: Mapped[int] = mapped_column(ForeignKey("series.id"))
    version: Mapped[int] = mapped_column(default=1)
    # JSON: {premisa, pregunta, destino, fuera[], episodios_recomendados,
    #        por_que, tramos: [{numero, titulo, pasa, cambia}]}
    contenido: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
