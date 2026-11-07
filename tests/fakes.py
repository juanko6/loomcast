"""Dobles de los `backend.clients.*`: misma firma pública, sin red, modelos ni GPU.

Cada fake registra sus llamadas en `.llamadas` y escribe archivos mínimos pero
válidos donde el cliente real los dejaría, para que las etapas del pipeline
puedan seguir leyéndolos. Se instalan con las fixtures de conftest.py.
"""
import subprocess
from pathlib import Path

from PIL import Image
from pydantic import BaseModel

from backend.clients.comfy import Liberacion


class FakeLLM:
    """`chat` devuelve la respuesta programada para el esquema pedido.

    `fake_llm.responder(TituloLLM, TituloLLM(...))` (o un dict, que se valida
    contra el esquema; para un RootModel de lista, la lista). Si una etapa llama
    varias veces al mismo esquema, `encadenar` programa una respuesta por
    llamada. Un esquema sin programar falla fuerte: mejor eso que devolver algo
    inventado.
    """

    PUBLICOS = ("chat", "ping")

    def __init__(self):
        self.llamadas: list[dict] = []
        self._respuestas: dict[type, object] = {}
        self._cadenas: dict[type, list] = {}

    def responder(self, esquema: type[BaseModel], respuesta) -> None:
        self._respuestas[esquema] = respuesta

    def encadenar(self, esquema: type[BaseModel], respuestas: list) -> None:
        self._cadenas[esquema] = list(respuestas)

    def chat(self, system: str, user: str, salida):
        self.llamadas.append({"system": system, "user": user, "salida": salida})
        if self._cadenas.get(salida):
            r = self._cadenas[salida].pop(0)
        elif salida in self._respuestas:
            r = self._respuestas[salida]
        else:
            raise AssertionError(f"FakeLLM sin respuesta para {salida.__name__}")
        return r if isinstance(r, BaseModel) else salida.model_validate(r)

    def ping(self, url=None) -> bool:
        return True


def _png(destino: Path, tam=(8, 8), modo="RGB") -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    Image.new(modo, tam, (10, 20, 30, 255) if modo == "RGBA" else (10, 20, 30)).save(
        destino, format="PNG"
    )


def _bytes(destino: Path, contenido: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)


class FakeComfy:
    PUBLICOS = (
        "generar_imagen", "editar_imagen", "upscale_imagen",
        "generar_video_i2v", "generar_video_loop", "generar_musica", "liberar_memoria",
    )

    def __init__(self):
        self.llamadas: list[tuple[str, dict]] = []

    def _reg(self, nombre, **kw):
        self.llamadas.append((nombre, kw))

    def nombres(self) -> list[str]:
        return [n for n, _ in self.llamadas]

    def generar_imagen(self, prompt, seed, destino, width=None, height=None, motor=None):
        self._reg("generar_imagen", prompt=prompt, seed=seed, destino=destino,
                  width=width, height=height, motor=motor)
        _png(Path(destino), (width or 8, height or 8))

    def editar_imagen(self, imagenes, prompt, seed, destino, motor=None,
                      width=None, height=None):
        self._reg("editar_imagen", imagenes=imagenes, prompt=prompt, seed=seed,
                  destino=destino, motor=motor, width=width, height=height)
        _png(Path(destino), (width or 8, height or 8))

    def upscale_imagen(self, origen, destino):
        self._reg("upscale_imagen", origen=origen, destino=destino)
        _png(Path(destino), (32, 32))

    def generar_video_i2v(self, imagen, prompt, seed, destino, motor=None):
        self._reg("generar_video_i2v", imagen=imagen, prompt=prompt, seed=seed,
                  motor=motor,
                  destino=destino)
        _bytes(Path(destino), b"fake-mp4")

    def generar_video_loop(self, imagen, prompt, seed, frames, fps, width, height, destino):
        self._reg("generar_video_loop", imagen=imagen, prompt=prompt, seed=seed,
                  frames=frames, fps=fps, width=width, height=height, destino=destino)
        _bytes(Path(destino), b"fake-mp4")

    def generar_musica(self, tags, lyrics, seed, duracion_s, bpm, keyscale, timesig,
                       idioma, destino, audio_codes=True, lm_temperature=0.85,
                       lm_device="cpu", tile_size=512, overlap=64):
        self._reg("generar_musica", tags=tags, lyrics=lyrics, seed=seed,
                  duracion_s=duracion_s, bpm=bpm, keyscale=keyscale,
                  timesig=timesig, idioma=idioma, destino=destino,
                  tile_size=tile_size, overlap=overlap)
        # Como el real: conserva la extensión del audio de origen (ACE-Step: FLAC).
        final = Path(destino).with_suffix(".flac")
        _bytes(final, b"fake-audio")
        return final

    def liberar_memoria(self, hasta_gb=None):
        self._reg("liberar_memoria", hasta_gb=hasta_gb)
        # Un ComfyUI con sitio de sobra: la memoria ya está donde hacía falta.
        libre = (hasta_gb or 0) + 5
        return Liberacion(libre, libre, 0.0, 1, True)


class FakeSTT:
    """`transcribir` devuelve las palabras programadas (por defecto, tres)."""

    PUBLICOS = ("transcribir", "liberar")

    def __init__(self):
        self.llamadas: list[dict] = []
        self.palabras = [
            {"word": " Hola", "start": 0.0, "end": 0.4},
            {"word": " mundo.", "start": 0.5, "end": 0.9},
            {"word": " Adiós", "start": 1.0, "end": 1.4},
        ]
        self.texto = "Hola mundo. Adiós"

    def transcribir(self, audio, *, palabras=False):
        self.llamadas.append({"audio": audio, "palabras": palabras})
        return {"texto": self.texto, "palabras": list(self.palabras) if palabras else []}

    def liberar(self):
        pass


class FakeRife:
    PUBLICOS = ("interpolar",)

    def __init__(self):
        self.llamadas: list[dict] = []

    def interpolar(self, entrada, salida, fps_origen, fps_final, frames=None):
        self.llamadas.append({"entrada": entrada, "salida": salida,
                              "fps_origen": fps_origen, "fps_final": fps_final,
                              "frames": frames})
        _bytes(Path(salida), b"fake-mp4")


class FakeEscalador:
    """Escala "x4" copiando cada cuadro a 4 veces su tamaño."""

    PUBLICOS = ("escalar_cuadros",)

    def __init__(self):
        self.llamadas: list[tuple[Path, Path]] = []

    def escalar_cuadros(self, entrada, salida, que_hacer=None):
        self.llamadas.append((entrada, salida))
        cuadros = sorted(Path(entrada).glob("*.png"))
        Path(salida).mkdir(parents=True, exist_ok=True)
        for i, c in enumerate(cuadros):
            if que_hacer:
                que_hacer(i, len(cuadros))
            with Image.open(c) as im:
                im.resize((im.width * 4, im.height * 4)).save(Path(salida) / c.name)


class FakeFondo:
    PUBLICOS = ("quitar_fondo",)

    def __init__(self):
        self.llamadas: list[tuple[Path, Path]] = []

    def quitar_fondo(self, origen, destino):
        self.llamadas.append((origen, destino))
        _png(Path(destino), modo="RGBA")


class FakeModeloTTS:
    """Qwen3-TTS de mentira: devuelve medio segundo de tono, en la forma
    `([audio], sample_rate)` que devuelve el modelo real."""

    SR = 24000

    def __init__(self, repo: str, llamadas: list):
        self.repo, self._llamadas = repo, llamadas

    def _onda(self):
        import numpy as np

        t = np.linspace(0, 0.5, self.SR // 2, endpoint=False)
        return [(0.2 * np.sin(2 * np.pi * 440 * t)).astype("float32")], self.SR

    def generate_voice_design(self, **kw):
        self._llamadas.append(("generate_voice_design", kw))
        return self._onda()

    def create_voice_clone_prompt(self, **kw):
        self._llamadas.append(("create_voice_clone_prompt", kw))
        return "prompt-clon"

    def generate_voice_clone(self, **kw):
        self._llamadas.append(("generate_voice_clone", kw))
        return self._onda()


class FakeTTS:
    """Registra qué modelo se carga/libera y qué se le pide (`.llamadas`)."""

    PUBLICOS = ("cargar_modelo", "liberar")

    def __init__(self):
        self.cargados: list[str] = []
        self.liberados = 0
        self.llamadas: list[tuple[str, dict]] = []

    def cargar_modelo(self, repo):
        self.cargados.append(repo)
        return FakeModeloTTS(repo, self.llamadas)

    def liberar(self):
        self.liberados += 1


class ProcesoFalso:
    """Lo que `procesos.ejecutar` necesita de un Popen, sin lanzar nada.

    Se construye desde una función con la firma de `subprocess.run`
    (`f(cmd, **kw) -> CompletedProcess`, o que lance `TimeoutExpired`), que es
    como están escritos los dobles de los tests: `procesos.ejecutar` pasó de
    `run` a `Popen` para poder cortar el proceso cuando se para un job, y este
    puente evita reescribirlos todos.
    """

    def __init__(self, cmd, correr, kw):
        self.args, self._correr, self._kw = cmd, correr, kw
        self.pid = id(self)
        self.returncode = None
        self._corrido = False

    def communicate(self, timeout=None):
        # `procesos.ejecutar` vuelve a llamar aquí tras matar un proceso que se
        # pasó de tiempo, para recoger lo que dejó. El doble solo corre una vez:
        # si no, el que lanza TimeoutExpired lo lanzaría dos veces.
        if self._corrido:
            return None, None
        self._corrido = True
        r = self._correr(self.args, timeout=timeout, **self._kw)
        self.returncode = r.returncode
        return r.stdout, r.stderr

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def popen_falso(correr):
    """Doble para `monkeypatch.setattr(subprocess, "Popen", popen_falso(f))`.

    Devuelve una clase y no una función porque, con el doble puesto, cualquier
    módulo que se importe después anota `subprocess.Popen | None` (lo hace
    llm_runtime) y una función no admite el `|` de las uniones de tipos.
    """

    class PopenFalso(ProcesoFalso):
        def __init__(self, cmd, **kw):
            super().__init__(cmd, correr, kw)

    return PopenFalso


# Capturado al importar, antes de que ningún test ponga su doble.
_POPEN_REAL = subprocess.Popen


def correr_de_verdad(cmd, timeout=None, **kw):
    """Ejecuta el proceso con el Popen auténtico aunque haya un doble puesto.

    Para los tests que solo quieren falsear un comando concreto: `subprocess.run`
    no sirve de escape, porque busca `Popen` en su módulo y encontraría el doble,
    llamando al doble otra vez (y otra).
    """
    p = _POPEN_REAL(cmd, **kw)
    salida, error = p.communicate(timeout=timeout)
    return subprocess.CompletedProcess(cmd, p.returncode, salida, error)
