"""Carga de config.toml (raíz del proyecto)."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "config.toml", "rb") as f:
    _cfg = tomllib.load(f)

_llm = _cfg["llm"]
LLM_URL: str = _llm["url"].rstrip("/")
LLM_MODEL: str = _llm.get("model", "local")
LLM_TIMEOUT_S: float = _llm.get("timeout_s", 600)
LLM_MAX_TOKENS: int = _llm.get("max_tokens", 4096)
# None → Loomcast no envía temperature (manda el sampling del llama-server).
LLM_TEMPERATURE: float | None = _llm.get("temperature")
# {} → no se envían chat_template_kwargs.
LLM_CHAT_TEMPLATE_KWARGS: dict = _llm.get("chat_template_kwargs", {})

COMFY_URL: str = _cfg["comfy"]["url"].rstrip("/")

_video = _cfg.get("video", {})
VIDEO_ENCODER: str = _video.get("encoder", "hardware")
VIDEO_BITRATE_MBPS: int = _video.get("bitrate_mbps", 12)
VIDEO_CRF: int = _video.get("crf", 18)

PROYECTOS_DIR: Path = ROOT / _cfg["paths"]["proyectos"]
PLANTILLAS_DIR: Path = ROOT / _cfg["paths"]["plantillas"]
VOCES_DIR: Path = ROOT / _cfg["paths"]["voces"]
DB_PATH: Path = ROOT / _cfg["paths"]["db"]
