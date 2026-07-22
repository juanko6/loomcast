from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_utc


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # generar_ideas | generar_guion | generar_metadatos | generar_voz | ...
    tipo: Mapped[str] = mapped_column()
    # id del tema o proyecto según el tipo
    ref_id: Mapped[int] = mapped_column()
    # Argumentos extra del handler, en JSON. ref_id no basta para jobs que
    # actúan sobre una parte del proyecto (p. ej. {"orden": 3, "modo": "i2v"}).
    params: Mapped[str] = mapped_column(Text, default="{}")
    # pendiente | corriendo | ok | error
    estado: Mapped[str] = mapped_column(default="pendiente")
    log: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
