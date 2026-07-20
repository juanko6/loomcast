"""Carga de plantillas de estilo (plantillas/<nombre>/), validadas con Pydantic."""
import json
from functools import lru_cache
from pathlib import Path

from ..config import PLANTILLAS_DIR
from ..schemas import Plantilla


class PlantillaNoEncontrada(KeyError):
    pass


@lru_cache
def cargar(nombre: str) -> dict:
    base = PLANTILLAS_DIR / nombre
    if not (base / "plantilla.json").exists():
        raise PlantillaNoEncontrada(nombre)
    with open(base / "plantilla.json") as f:
        data = Plantilla.model_validate(json.load(f)).model_dump()
    data["prompts"] = {
        p.stem: p.read_text() for p in (base / "prompts").glob("*.md")
    }
    return data


def listar() -> list[str]:
    return sorted(
        p.name for p in Path(PLANTILLAS_DIR).iterdir()
        if (p / "plantilla.json").exists()
    )
