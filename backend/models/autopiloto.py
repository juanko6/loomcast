from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc

# Las tres paradas de revisión del flujo de hoy, en el orden en que llegan. Son
# las claves que viajan en `Autopiloto.paradas`.
#
#  - `idea`: qué ideas se producen. En un lote es quien decide el reparto de
#    proyectos (solo las aprobadas a mano, o todas las propuestas si se
#    desactiva); en el autopiloto de un proyecto suelto ya está pasada, porque
#    el proyecto existe justo porque alguien aprobó su idea.
#  - `guion`: el texto que lo decide todo. Es la parada más barata de atender y
#    la más cara de saltarse: media hora de GPU sobre un guion malo.
#  - `escenas`: los prompts de escena antes de gastar GPU en las imágenes.
PARADAS = ("idea", "guion", "escenas")

# Tras qué etapa espera cada parada. El resto de las etapas no paran a nadie.
PARADA_TRAS = {"generar_guion": "guion", "generar_escenas": "escenas"}

# Estados de un autopiloto:
#  - `pendiente`: es de un lote y espera su turno (la cola es de un solo hilo a
#    propósito, así que los proyectos de un lote se producen de uno en uno).
#  - `corriendo`: tiene una etapa en la cola o entre manos.
#  - `esperando`: llegó a una parada de revisión y espera a que alguien mire.
#    No encola nada por su cuenta: hay que decirle «continuar».
#  - `hecho`: el proyecto llegó a su final.mp4.
#  - `error`: una etapa falló por algo que no se arregla repitiendo.
#  - `parado`: alguien lo paró (el botón rojo, o el de este proyecto).
VIVOS = ("pendiente", "corriendo", "esperando")
TERMINADOS = ("hecho", "error", "parado")


class Lote(Base):
    """Varias ideas de un tema produciéndose una detrás de otra.

    Un lote no ejecuta nada: es el grupo y el **orden**. Lo que produce es un
    `Autopiloto` por proyecto, y solo uno está `corriendo` a la vez porque la
    cola de jobs es de un solo hilo a propósito (las etapas se pelean por la
    misma memoria unificada). Cuando el que corría deja la línea —porque acabó,
    porque falló o porque se paró en una revisión— arranca el siguiente
    `pendiente` del lote.

    El lote no tiene estado propio: se deduce de los autopilotos que lo forman.
    Tenerlo escrito en dos sitios obligaría a decidir qué significa un lote
    «hecho» con tres proyectos esperando revisión, y no significa nada.
    """

    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Tema del que salieron las ideas. Es lo que la UI enseña para distinguir un
    # lote de otro.
    tema_id: Mapped[int] = mapped_column(ForeignKey("temas.id"))
    created_at: Mapped[datetime] = mapped_column(default=now_utc)


class Autopiloto(Base):
    """Una tirada automática de un proyecto: de donde esté hasta su final.mp4.

    No es una etapa más ni un job largo: es **estado**, y quien lo mueve es la
    cola. Al terminar bien una etapa, el worker le pregunta qué falta
    (`services/autopiloto.py`), y el autopiloto encola la siguiente o se queda
    esperando en una parada de revisión. Que viva en la base y no en memoria es
    lo que hace que un reinicio del backend lo retome donde estaba, igual que
    `recuperar_pendientes()` retoma la cola.

    Y lo que importa de que NO se encole él solo desde dentro de una etapa: la
    parada en caliente ya corta el job que corre y vacía la cola, así que un
    autopiloto que re-encolara por su cuenta sería justo lo que no se puede
    detener. Aquí el único que encola es el worker, y solo tras una etapa que
    terminó bien y sin que se pidiera parar.
    """

    __tablename__ = "autopilotos"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    # Lote del que forma parte, o None si es el autopiloto de un proyecto suelto
    # (lanzado desde su propia vista).
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes.id"), default=None)
    estado: Mapped[str] = mapped_column(default="corriendo")
    # Modo de montaje del vídeo, elegido al lanzarlo: igual que se elige en el
    # paso de vídeo, porque es la misma decisión y no tiene un valor obvio.
    modo_video: Mapped[str] = mapped_column(default="kenburns")
    # Motor i2v ([i2v.motores] de config.toml); vacío = el de [i2v].motor. Solo
    # lo miran los modos que animan con i2v.
    motor: Mapped[str] = mapped_column(default="")
    # Con qué narra: "clon" clona la voz del banco que se eligió al lanzar, y
    # "design" la escribe VoiceDesign con el estilo que el LLM sacó de esta
    # historia. Va en la fila y no en los kwargs del job porque la etapa de voz
    # se encola etapas más tarde, cuando ya nadie recuerda qué se pidió.
    narracion: Mapped[str] = mapped_column(default="clon")
    # Paradas de revisión que respeta, en CSV. Vacío = producción sin manos.
    paradas: Mapped[str] = mapped_column(default=",".join(PARADAS))
    # Última etapa que terminó bien. Es de donde sale qué toca ahora al pulsar
    # «continuar» tras una revisión, y lo que la UI enseña mientras trabaja.
    etapa: Mapped[str] = mapped_column(default="")
    # Etapas que esta tirada ha encolado. Es el tope de seguridad: el freno de
    # "lo que falta es justo lo que acaba de terminar" pilla una etapa que se
    # repite, pero no un ciclo de dos (un montaje que dice que terminó sin
    # dejar el final.mp4 vuelve al primer job del modo, y ese al montaje). La
    # escalera entera son unas diez etapas, así que pasar del tope significa
    # que la tirada no avanza.
    encoladas: Mapped[int] = mapped_column(default=0)
    # Por qué está donde está, en castellano y para leerlo: «Esperando que
    # revises el guion», «Falló el montaje: …». Es lo que contesta a «¿y por qué
    # se ha parado esto?».
    motivo: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def paradas_activas(self) -> list[str]:
        return [p for p in (self.paradas or "").split(",") if p]
