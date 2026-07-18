"""Carga de config.toml (raíz del proyecto)."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "config.toml", "rb") as f:
    _cfg = tomllib.load(f)

LLM_URL: str = _cfg["llm"]["url"].rstrip("/")
LLM_MODEL: str = _cfg["llm"]["model"]
LLM_TEMPERATURE: float = _cfg["llm"]["temperature"]
LLM_TIMEOUT_S: float = _cfg["llm"]["timeout_s"]

COMFY_URL: str = _cfg["comfy"]["url"].rstrip("/")

PROYECTOS_DIR: Path = ROOT / _cfg["paths"]["proyectos"]
PLANTILLAS_DIR: Path = ROOT / _cfg["paths"]["plantillas"]
DB_PATH: Path = ROOT / _cfg["paths"]["db"]
