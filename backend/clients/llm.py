"""Cliente para llama-server (API OpenAI-compatible) con contratos Pydantic.

El modelo Pydantic de salida cumple doble función: su JSON schema restringe
la generación en el servidor (grammar), y la respuesta se valida y parsea
con él antes de entrar al resto del sistema.
"""
import json
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .. import parada
from ..config import LLM_MODELOS, ModeloLLM

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


# Modelo al que apuntan las llamadas. Lo empuja `services/llm_runtime`, que es
# quien sabe cuál está realmente cargado; así el cliente no consulta la BD ni
# depende de una capa superior.
_activo: ModeloLLM = LLM_MODELOS[0]


def configurar(modelo: ModeloLLM) -> None:
    global _activo
    _activo = modelo


def activo() -> ModeloLLM:
    return _activo


def _extract_json(text: str) -> dict | list:
    """Tolera fences de markdown y texto alrededor del JSON."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
        if start == -1:
            raise LLMError(f"El modelo no devolvió JSON: {text[:300]}")
        for end in range(len(text), start, -1):
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
        try:
            return json.loads(_reparar_json(text[start : text.rfind("}") + 1]))
        except json.JSONDecodeError:
            pass
        raise LLMError(f"JSON inválido del modelo: {text[:300]}")


# Una cadena (o un número) al final de una línea seguida de otra clave: falta la coma.
_COMA_QUE_FALTA = re.compile(r'(?<=[0-9"])(\s*\n\s*)(?="[^"\n]+"\s*:)')
# Cadenas sueltas en fila cuya siguiente no es una clave: son el mismo valor partido.
_CADENA_PARTIDA = re.compile(r'(?<!\\)"\s*,\s*\n\s*"(?![^"\n]*"\s*:)')


def _reparar_json(text: str) -> str:
    """Arregla los dos fallos de forma que comete el modelo de MLX, que ignora el json_schema.

    Con el guion de secciones de la música, el Qwen 4-bit a veces escribe cada
    marcador como una cadena aparte (`"lyrics": "[Intro]",\n"[Tema A]",\n...`)
    en vez de una sola con saltos de línea, y a veces se come la coma antes de la
    clave siguiente. El contenido está entero; solo la forma está mal, y la
    respuesta es determinista, así que reintentar devuelve exactamente lo mismo.
    """
    text = _CADENA_PARTIDA.sub(r"\\n", text)
    return _COMA_QUE_FALTA.sub(r",\1", text)


class LLMTruncado(LLMError):
    """La respuesta se cortó por el límite de tokens, no por estar mal.

    Se distingue del resto porque el arreglo es otro: subir `max_tokens` en
    config.toml, no cambiar de modelo ni tocar el prompt. Sin esto, un guion
    largo acaba como "JSON inválido del modelo" y parece que el modelo escribe
    mal cuando lo que pasa es que no le dejaron terminar.
    """


def _completar(client: httpx.Client, url: str, body: dict) -> str:
    """Pide la respuesta **en streaming** y la junta.

    El streaming no es para enseñar el texto mientras sale —ninguna etapa lo
    aprovecha— sino para poder parar. Con la respuesta de un tirón, el hilo de la
    cola se queda bloqueado dentro de httpx hasta que el modelo termina el guion
    entero, y pulsar "Parar" no lo toca: el job se marcaría cancelado minutos
    después, con el modelo ocupando la memoria todo ese rato. Leyendo por trozos
    se puede mirar la bandera entre uno y otro, y salir cierra la conexión, con
    lo que el servidor abandona la generación.

    El corte llega como muy tarde en el trozo siguiente; lo que no se puede
    partir es la lectura del prompt, antes del primer trozo.

    El formato es el SSE de la API de OpenAI, que hablan igual llama-server y
    mlx_lm.server. El contenido se valida igual que antes al volver a `chat`:
    mlx_lm ignora `json_schema`, así que no se puede dar por hecho que lo que
    llegue cumpla el contrato.
    """
    trozos: list[str] = []
    razon = None
    with client.stream(
        "POST", f"{url}/v1/chat/completions", json=body | {"stream": True}
    ) as r:
        if r.status_code >= 400:
            r.read()
            raise LLMError(f"El servidor del LLM respondió {r.status_code}: {r.text[:300]}")
        for linea in r.iter_lines():
            parada.comprobar("generando texto")
            if not linea.startswith("data:"):
                continue
            datos = linea[5:].strip()
            if not datos or datos == "[DONE]":
                continue
            try:
                trozo = json.loads(datos)
            except json.JSONDecodeError:
                raise LLMError(
                    f"El servidor del LLM mandó un trozo que no es JSON: {datos[:200]}"
                )
            # Algunos servidores cierran con un trozo sin `choices` (solo el
            # recuento de tokens), y otros mandan `delta` vacíos por el camino.
            eleccion = (trozo.get("choices") or [{}])[0]
            trozos.append((eleccion.get("delta") or {}).get("content") or "")
            razon = eleccion.get("finish_reason") or razon
    contenido = "".join(trozos)
    if razon == "length":
        raise LLMTruncado(
            f"El modelo se quedó sin tokens a mitad de la respuesta "
            f"(max_tokens = {body.get('max_tokens')}). Súbelo en config.toml, "
            f"en [llm] o en el modelo. Lo que alcanzó a escribir: "
            f"{contenido[-200:]}"
        )
    return contenido


def _cuerpo(system: str, user: str) -> dict:
    # El sampling lo define el llama-server (tu script de arranque); Loomcast
    # solo añade temperature o chat_template_kwargs si están en config.toml.
    m = _activo
    base = {
        "model": m.model,
        "max_tokens": m.max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if m.temperature is not None:
        base["temperature"] = m.temperature
    if m.chat_template_kwargs:
        base["chat_template_kwargs"] = m.chat_template_kwargs
    return base


def _limpiar_texto(text: str) -> str:
    """Un párrafo suelto, venga como venga: sin fences de markdown, sin
    comillas alrededor y en una sola línea. Si el modelo contestó un JSON de
    todos modos, se queda con su primer texto."""
    text = text.strip()
    fence = re.search(r"```(?:\w+)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if text.startswith("{"):
        try:
            datos = json.loads(text)
            text = next((v for v in datos.values() if isinstance(v, str)), text) \
                if isinstance(datos, dict) else text
        except json.JSONDecodeError:
            pass
    text = " ".join(text.split())
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def texto(system: str, user: str, minimo: int = 20) -> str:
    """Chat cuya respuesta es un párrafo de texto, sin contrato JSON.

    Para salidas de un solo texto. Pedirlas como JSON no compensa con el Qwen
    MLX: mlx_lm ignora `json_schema` y, con algunos prompts, contesta el
    párrafo en prosa aunque se le pida el objeto (medido el 2026-11-08 con la
    escena de la galería: la misma petición salía en JSON o en prosa según la
    guía del estilo).
    """
    m = _activo
    with httpx.Client(timeout=m.timeout_s) as client:
        contenido = _completar(client, m.url, _cuerpo(system, user))
    limpio = _limpiar_texto(contenido)
    if len(limpio) < minimo:
        raise LLMError(f"El modelo devolvió un texto demasiado corto: {contenido[:300]!r}")
    return limpio


def chat(system: str, user: str, salida: type[T]) -> T:
    """Chat completion cuya respuesta debe cumplir el contrato `salida`.

    Pide generación restringida por json_schema; si el servidor no lo
    soporta (4xx), reintenta en modo texto. En ambos casos la respuesta
    pasa por la validación Pydantic antes de devolverse.
    """
    m = _activo
    base = _cuerpo(system, user)
    with httpx.Client(timeout=m.timeout_s) as client:
        con_schema = base | {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "salida",
                    "schema": salida.model_json_schema(),
                    "strict": True,
                },
            }
        }
        try:
            contenido = _completar(client, m.url, con_schema)
        except LLMTruncado:
            # Reintentar sin schema daría exactamente el mismo corte.
            raise
        except LLMError:
            contenido = _completar(client, m.url, base)

    try:
        return salida.model_validate(_extract_json(contenido))
    except ValidationError as e:
        raise LLMError(
            f"La salida del LLM no cumple el contrato {salida.__name__}: "
            f"{e.errors()[:3]} — contenido: {contenido[:300]}"
        )


def ping(url: str | None = None) -> bool:
    """¿Responde el llama-server? Sin `url`, la del modelo activo."""
    try:
        with httpx.Client(timeout=3) as client:
            return client.get(f"{url or _activo.url}/v1/models").status_code < 400
    except httpx.HTTPError:
        return False


def que_hay(url: str | None = None) -> tuple[str, float] | None:
    """Qué modelo sirve esa url y cuántos GiB de pesos tiene dentro, según él.

    Sale de `/v1/models` de llama-server: `data[0].id` es el alias (`-a`) y
    `meta.size` los bytes del gguf cargado. Hace falta porque todos tus modelos
    comparten el 9876, así que lo que de verdad escucha ahí puede no ser el que
    marca la UI, y porque al pararlo hay que esperar *su* memoria y no la que
    declare config.toml de otro.

    None si no responde o no lo cuenta: es información para el log, no una
    condición, así que nunca lanza.
    """
    try:
        with httpx.Client(timeout=3) as client:
            r = client.get(f"{url or _activo.url}/v1/models")
            r.raise_for_status()
            datos = r.json()["data"][0]
        return str(datos["id"]), float(datos["meta"]["size"]) / (1024**3)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None
