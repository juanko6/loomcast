"""Engine y sesiones SQLite (acceso desde API y worker en hilos distintos)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DB_PATH
from .models import Base

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
