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

@dataclass(frozen=True)
class MotorImagen:
    """Un motor de imagen declarado en [imagen.motores.*] de config.toml.

    Cada motor sabe hacer los modos para los que declara workflow: `generar`
    (texto→imagen) y/o `editar` (instruct-edit sobre una imagen subida). Los que
    no declara simplemente no aparecen como opción en ese modo.
    """

    id: str
    nombre: str
    generar: str | None
    editar: str | None

    def workflow(self, modo: str) -> str | None:
        return self.generar if modo == "generar" else self.editar

    @property
    def modos(self) -> list[str]:
        return [m for m in ("generar", "editar") if self.workflow(m)]


_imagen = _cfg.get("imagen", {})
IMAGEN_MOTORES: dict[str, MotorImagen] = {
    id_: MotorImagen(
        id=id_,
        nombre=bruto.get("nombre", id_),
        generar=bruto.get("generar"),
        editar=bruto.get("editar"),
    )
    for id_, bruto in _imagen.get("motores", {}).items()
}
if not IMAGEN_MOTORES:
    raise ValueError("config.toml no declara ningún [imagen.motores.*]")
for _motor in IMAGEN_MOTORES.values():
    if not _motor.modos:
        raise ValueError(
            f"El motor de imagen '{_motor.id}' no declara ni 'generar' ni 'editar'"
        )

IMAGEN_MOTOR_GENERAR: str = _imagen.get("motor_generar", "zimage")
IMAGEN_MOTOR_EDITAR: str = _imagen.get("motor_editar", "qwen")
for _modo, _defecto in (("generar", IMAGEN_MOTOR_GENERAR), ("editar", IMAGEN_MOTOR_EDITAR)):
    _m = IMAGEN_MOTORES.get(_defecto)
    if _m is None or _modo not in _m.modos:
        raise ValueError(
            f"[imagen].motor_{_modo} = '{_defecto}' no existe o no sabe {_modo}. "
            f"Motores que sí: {[m.id for m in IMAGEN_MOTORES.values() if _modo in m.modos]}"
        )

IMAGEN_WIDTH: int = _imagen.get("width", 768)
IMAGEN_HEIGHT: int = _imagen.get("height", 1344)

# Generación de música (ACE-Step 1.5). Como en [i2v]/[edicion], apunta a un
# workflow de ComfyUI en formato API con los placeholders {TAGS}, {LYRICS},
# {SEED}, {DURACION}, {BPM}, {KEYSCALE}, {TIMESIG}, {IDIOMA} y {AUDIO_CODES}.
_musica = _cfg.get("musica", {})
MUSICA_WORKFLOW: str = _musica.get("workflow", "workflows/musica_api.json")
MUSICA_DURACION_S: int = _musica.get("duracion_s", 30)
MUSICA_AUDIO_CODES: bool = _musica.get("audio_codes", True)
# Temperatura del LM planificador: a 0 (argmax) las pistas salen monótonas.
MUSICA_LM_TEMPERATURE: float = float(_musica.get("lm_temperature", 0.85))
# Dónde corre el LM. "default" (GPU) exige el parche de
# scripts/instalar_parche_mps.py, que esquiva el bug de torch.multinomial en
# Metal; "cpu" no depende de nada pero es ~7× más lento. Ver [musica] en
# config.toml.
MUSICA_LM_DEVICE: str = _musica.get("lm_device", "default")
# Masterizado EBU R128 de la pista ya generada. lufs = 0 lo desactiva.
MUSICA_LUFS: float = float(_musica.get("lufs", -14.0))
MUSICA_TRUE_PEAK: float = float(_musica.get("true_peak", -1.0))

PROYECTOS_DIR: Path = ROOT / _cfg["paths"]["proyectos"]
PLANTILLAS_DIR: Path = ROOT / _cfg["paths"]["plantillas"]
VOCES_DIR: Path = ROOT / _cfg["paths"]["voces"]
GALERIA_DIR: Path = ROOT / _cfg["paths"].get("galeria", "galeria")
MUSICA_DIR: Path = ROOT / _cfg["paths"].get("musica", "musica")
PROMPTS_DIR: Path = ROOT / "prompts"
DB_PATH: Path = ROOT / _cfg["paths"]["db"]
