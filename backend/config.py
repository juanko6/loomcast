"""Carga de config.toml (raíz del proyecto)."""
import os
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
LLM_ESPERA_DEVOLUCION_S: float = float(_llm.get("espera_devolucion_s", 20))


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
    # GiB de memoria unificada libres que hacen falta para cargarlo. No se
    # reserva nada: es la condición que se comprueba antes de lanzarlo, para no
    # pedirle al kernel más de lo que hay (ver services/llm_runtime.py).
    memoria_gb: float

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
        memoria_gb=bruto.get("memoria_gb", _llm.get("memoria_gb", 20)),
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
COMFY_ESPERA_LIBERACION_S: float = _cfg["comfy"].get("espera_liberacion_s", 20)

# Cola de jobs: reintentos de lo que falla por algo transitorio.
_cola = _cfg.get("cola", {})
COLA_INTENTOS: int = _cola.get("intentos", 3)
COLA_ESPERA_S: float = _cola.get("espera_s", 20)
# GiB libres que la cola espera a ver antes de dejar que una etapa cargue un
# modelo DENTRO del backend (Qwen3-TTS, whisper). No reserva nada: pide el
# `/free` a ComfyUI y espera a medir la bajada, porque el `/free` que lanzó la
# etapa anterior al acabar es a ciegas (vuelve en 1 ms con los pesos dentro).
# 8 sobra para el TTS en fp16 (3,4 GiB de pesos y un pico medido de 4,2) y no
# llega a bloquear nunca; es el aviso de que la memoria la tiene otra cosa.
COLA_MEMORIA_MODELO_GB: float = float(_cola.get("memoria_modelo_gb", 8))

# Autopiloto: qué paradas de revisión respeta por defecto (ver [autopiloto] en
# config.toml). Las tres de siempre, porque es lo que ya hace el flujo a mano.
_autopiloto = _cfg.get("autopiloto", {})
AUTOPILOTO_PARADAS: tuple[str, ...] = tuple(
    _autopiloto.get("paradas", ["idea", "guion", "escenas"])
)
# Si el autopiloto le pone banda sonora al vídeo. Puesto, la escribe desde la
# historia y la mezcla bajo la voz; quitado, el vídeo sale solo con narración.
AUTOPILOTO_MUSICA: bool = bool(_autopiloto.get("musica", True))

# --- memoria de PyTorch en MPS ----------------------------------------------
# Lo que de verdad mandaba la voz al swap. El asignador de MPS **cachea** los
# bloques que libera, y en una generación autorregresiva cada paso pide una
# forma un poco distinta de la del paso anterior: no puede reutilizar nada de lo
# cacheado y le pide a Metal un bloque nuevo cada vez, mil veces seguidas.
#
# Medido en este M3 Max (48 GiB; `recommended_max_memory` = 37,4), narrando el
# guion de un episodio en un proceso a solas, sin LLM ni ComfyUI dentro:
#
#            texto    audio     pico MPS     swapouts   tiempo
#   sin tope  200 pal  93,4 s    53,1 GiB    +76,2 GiB    212 s
#   con tope  200 pal  88,8 s    15,6 GiB     +0,0 GiB     95 s
#   con tope  400 pal 185,3 s    16,3 GiB     +0,3 GiB    204 s
#
# O sea: el pico no era el modelo (1,7B en fp16: 4,7 GiB cargado) ni crecía con
# la longitud del guion — crecía con el número de pasos porque nadie soltaba lo
# cacheado. Con los topes puestos el pico queda plano en ~16 GiB por largo que
# sea el texto, no hay swap y tarda la mitad.
#
# Son fracciones de `recommended_max_memory`: al cruzar el alto, el asignador
# suelta lo cacheado hasta bajar del bajo, en vez de crecer sin freno. 0,55 son
# 20,6 GiB aquí, con holgura de sobra sobre los 16 que de verdad pide (y si se
# cruzara, torch lanza "MPS backend out of memory", que es un error honesto y no
# media hora de swap).
#
# Van al **entorno** y no a una llamada porque torch los lee al inicializar el
# asignador, antes de que ninguna etapa pueda tocarlos; esto corre antes porque
# en todo el backend `import torch` está dentro de las funciones, nunca arriba.
# Con `setdefault`, si los exportas tú manda lo tuyo.
_voz = _cfg.get("voz", {})
VOZ_MPS_TOPE: float = float(_voz.get("mps_tope", 0.55))
VOZ_MPS_TOPE_BAJO: float = float(_voz.get("mps_tope_bajo", 0.40))
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", str(VOZ_MPS_TOPE))
os.environ.setdefault("PYTORCH_MPS_LOW_WATERMARK_RATIO", str(VOZ_MPS_TOPE_BAJO))

_stt = _cfg.get("stt", {})
STT_MODELO: str = _stt.get("modelo", "turbo")
STT_DISPOSITIVO: str = _stt.get("dispositivo", "auto")
STT_COMPUTE_TYPE: str = _stt.get("compute_type", "int8")
# "" → sin idioma fijo: que lo detecte Whisper.
STT_IDIOMA: str | None = _stt.get("idioma", "es") or None

_video = _cfg.get("video", {})
VIDEO_ENCODER: str = _video.get("encoder", "hardware")
VIDEO_BITRATE_MBPS: int = _video.get("bitrate_mbps", 12)
VIDEO_CRF: int = _video.get("crf", 18)
VIDEO_COLA_FINAL_S: float = _video.get("cola_final_s", 1.5)
# Mezcla de la música del proyecto en el armado (ver [video] en config.toml).
VIDEO_MUSICA_DB: float = float(_video.get("musica_db", -16.0))
VIDEO_MUSICA_FADE_S: float = float(_video.get("musica_fade_s", 2.0))

@dataclass(frozen=True)
class MotorI2V:
    """Un motor de image-to-video declarado en [i2v.motores.*] de config.toml.

    `frames` y `fps_origen` viajan con el motor y no en [i2v] porque son
    propiedad del modelo: cada uno admite una forma de cuadros (HunyuanVideo y
    LTX quieren 4n+1) y entrega a su cadencia, que es la que determina cuánto
    tiene que interpolar RIFE.
    """

    id: str
    nombre: str
    workflow: str
    frames: int
    fps_origen: int


_i2v = _cfg.get("i2v", {})
I2V_MOTORES: dict[str, MotorI2V] = {
    id_: MotorI2V(
        id=id_,
        nombre=bruto.get("nombre", id_),
        workflow=bruto["workflow"],
        frames=int(bruto.get("frames", 21)),
        fps_origen=int(bruto.get("fps_origen", 24)),
    )
    for id_, bruto in _i2v.get("motores", {}).items()
}
if not I2V_MOTORES:
    raise ValueError("config.toml no declara ningún [i2v.motores.*]")

I2V_MOTOR: str = _i2v.get("motor", next(iter(I2V_MOTORES)))
if I2V_MOTOR not in I2V_MOTORES:
    raise ValueError(
        f"[i2v].motor = '{I2V_MOTOR}' no existe. "
        f"Motores declarados: {sorted(I2V_MOTORES)}"
    )

I2V_FPS_FINAL: int = _i2v.get("fps_final", 48)


def motor_i2v(id_: str | None = None) -> MotorI2V:
    """El motor i2v pedido, o el de [i2v].motor si no se pide ninguno."""
    motor = I2V_MOTORES.get(id_ or I2V_MOTOR)
    if motor is None:
        raise ValueError(
            f"No existe el motor i2v '{id_}'. Declarados: {sorted(I2V_MOTORES)}"
        )
    return motor

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

# Retratos de referencia del reparto ([personajes] de config.toml).
_personajes = _cfg.get("personajes", {})
PERSONAJE_MOTOR: str = _personajes.get("motor", IMAGEN_MOTOR_GENERAR)
PERSONAJE_WIDTH: int = int(_personajes.get("width", 768))
PERSONAJE_HEIGHT: int = int(_personajes.get("height", 1024))
PERSONAJE_MOTOR_ESCENA: str = _personajes.get("motor_escena", IMAGEN_MOTOR_EDITAR)
for _clave, _id, _modo in (
    ("motor", PERSONAJE_MOTOR, "generar"),
    ("motor_escena", PERSONAJE_MOTOR_ESCENA, "editar"),
):
    _m = IMAGEN_MOTORES.get(_id)
    if _m is None or _modo not in _m.modos:
        raise ValueError(
            f"[personajes].{_clave} = '{_id}' no existe o no sabe {_modo}. "
            f"Motores que sí: "
            f"{[m.id for m in IMAGEN_MOTORES.values() if _modo in m.modos]}"
        )

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
# scripts/instalar_parches.py, que esquiva el bug de torch.multinomial en
# Metal; "cpu" no depende de nada pero es ~7× más lento. Ver [musica] en
# config.toml.
MUSICA_LM_DEVICE: str = _musica.get("lm_device", "default")
# Masterizado EBU R128 de la pista ya generada. lufs = 0 lo desactiva.
MUSICA_LUFS: float = float(_musica.get("lufs", -14.0))
MUSICA_TRUE_PEAK: float = float(_musica.get("true_peak", -1.0))
# Corrección de imagen estéreo: dB que el canal central debe sacarle al lateral.
# Por debajo de `min` se baja el lateral hasta `objetivo`. Ver [musica].
MUSICA_MEDIO_LADO_MIN: float = float(_musica.get("medio_lado_min", 3.0))
MUSICA_MEDIO_LADO_OBJETIVO: float = float(_musica.get("medio_lado_objetivo", 6.0))
# Lado en píxeles de la portada cuadrada de cada pista.
MUSICA_PORTADA_PX: int = int(_musica.get("portada_px", 384))

PROYECTOS_DIR: Path = ROOT / _cfg["paths"]["proyectos"]
PLANTILLAS_DIR: Path = ROOT / _cfg["paths"]["plantillas"]
VOCES_DIR: Path = ROOT / _cfg["paths"]["voces"]
REPARTO_DIR: Path = ROOT / _cfg["paths"].get("reparto", "reparto")
GALERIA_DIR: Path = ROOT / _cfg["paths"].get("galeria", "galeria")
MUSICA_DIR: Path = ROOT / _cfg["paths"].get("musica", "musica")
PROMPTS_DIR: Path = ROOT / "prompts"
DB_PATH: Path = ROOT / _cfg["paths"]["db"]
