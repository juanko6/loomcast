"""Carga de config.toml (raíz del proyecto)."""
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "config.toml", "rb") as f:
    _cfg = tomllib.load(f)

_llm = _cfg["llm"]
LLM_AUTOSTART: bool = _llm.get("autostart", False)
LLM_INACTIVIDAD_S: float = _llm.get("inactividad_s", 300)
LLM_ESPERA_ARRANQUE_S: float = _llm.get("espera_arranque_s", 240)


@dataclass(frozen=True)
class ModeloLLM:
    """Un llama-server declarado en config.toml.

    `comando` es el script que lo levanta; si es None, el modelo es externo:
    Loomcast lo usa donde esté pero nunca lo arranca ni lo para.
    """

    id: str
    nombre: str
    url: str
    comando: str | None
    model: str
    timeout_s: float
    max_tokens: int
    # None → Loomcast no envía temperature (manda el sampling del llama-server).
    temperature: float | None
    # {} → no se envían chat_template_kwargs.
    chat_template_kwargs: dict

    @property
    def gestionado(self) -> bool:
        return LLM_AUTOSTART and self.comando is not None


def _modelo(bruto: dict) -> ModeloLLM:
    """Construye un modelo heredando de [llm] lo que no declare."""
    return ModeloLLM(
        id=bruto["id"],
        nombre=bruto.get("nombre", bruto["id"]),
        url=bruto.get("url", _llm.get("url", "http://127.0.0.1:9876")).rstrip("/"),
        comando=bruto.get("comando"),
        model=bruto.get("model", _llm.get("model", "local")),
        timeout_s=bruto.get("timeout_s", _llm.get("timeout_s", 600)),
        max_tokens=bruto.get("max_tokens", _llm.get("max_tokens", 4096)),
        temperature=bruto.get("temperature", _llm.get("temperature")),
        chat_template_kwargs=bruto.get(
            "chat_template_kwargs", _llm.get("chat_template_kwargs", {})
        ),
    )


# Sin [[llm.modelos]] declarados, [llm] describe por sí solo un único modelo
# externo: config.toml de antes del selector sigue funcionando igual.
LLM_MODELOS: list[ModeloLLM] = [
    _modelo(m) for m in _llm.get("modelos", [{"id": "manual", "nombre": "llama-server"}])
]
_ids = [m.id for m in LLM_MODELOS]
if len(_ids) != len(set(_ids)):
    raise ValueError(f"Hay ids repetidos en [[llm.modelos]] de config.toml: {_ids}")

LLM_LOGS_DIR: Path = ROOT / "logs"

COMFY_URL: str = _cfg["comfy"]["url"].rstrip("/")
COMFY_TIMEOUT_S: float = _cfg["comfy"].get("timeout_s", 1800)

_video = _cfg.get("video", {})
VIDEO_ENCODER: str = _video.get("encoder", "hardware")
VIDEO_BITRATE_MBPS: int = _video.get("bitrate_mbps", 12)
VIDEO_CRF: int = _video.get("crf", 18)
VIDEO_COLA_FINAL_S: float = _video.get("cola_final_s", 1.5)

_i2v = _cfg.get("i2v", {})
I2V_WORKFLOW: str = _i2v.get("workflow", "workflows/i2v_api.json")
I2V_FRAMES: int = _i2v.get("frames", 21)
I2V_FPS_ORIGEN: int = _i2v.get("fps_origen", 24)
I2V_FPS_FINAL: int = _i2v.get("fps_final", 48)

_rife = _cfg.get("rife", {})
RIFE_BIN: str = _rife.get("bin", "tools/rife-ncnn-vulkan-20221029-macos/rife-ncnn-vulkan")
RIFE_MODELO: str = _rife.get("modelo", "rife-v4.6")

# Edición de imágenes (galería): workflow de ComfyUI con un modelo instruct-edit
# (Qwen-Image-Edit, Flux Kontext…) que el usuario exporta en formato API con los
# placeholders {IMAGE}, {PROMPT} y {SEED}, igual que el de i2v.
_edicion = _cfg.get("edicion", {})
EDIT_WORKFLOW: str = _edicion.get("workflow", "workflows/qwen_edit_api.json")

PROYECTOS_DIR: Path = ROOT / _cfg["paths"]["proyectos"]
PLANTILLAS_DIR: Path = ROOT / _cfg["paths"]["plantillas"]
VOCES_DIR: Path = ROOT / _cfg["paths"]["voces"]
GALERIA_DIR: Path = ROOT / _cfg["paths"].get("galeria", "galeria")
PROMPTS_DIR: Path = ROOT / "prompts"
DB_PATH: Path = ROOT / _cfg["paths"]["db"]
