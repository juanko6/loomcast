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
        raise LLMError(f"JSON inválido del modelo: {text[:300]}")


class LLMTruncado(LLMError):
    """La respuesta se cortó por el límite de tokens, no por estar mal.

    Se distingue del resto porque el arreglo es otro: subir `max_tokens` en
    config.toml, no cambiar de modelo ni tocar el prompt. Sin esto, un guion
    largo acaba como "JSON inválido del modelo" y parece que el modelo escribe
    mal cuando lo que pasa es que no le dejaron terminar.
    """


def _completar(client: httpx.Client, url: str, body: dict) -> str:
    r = client.post(f"{url}/v1/chat/completions", json=body)
    if r.status_code >= 400:
        raise LLMError(f"El servidor del LLM respondió {r.status_code}: {r.text[:300]}")
    eleccion = r.json()["choices"][0]
    contenido = eleccion["message"]["content"]
    if eleccion.get("finish_reason") == "length":
        raise LLMTruncado(
            f"El modelo se quedó sin tokens a mitad de la respuesta "
            f"(max_tokens = {body.get('max_tokens')}). Súbelo en config.toml, "
            f"en [llm] o en el modelo. Lo que alcanzó a escribir: "
            f"{contenido[-200:]}"
        )
    return contenido


def chat(system: str, user: str, salida: type[T]) -> T:
    """Chat completion cuya respuesta debe cumplir el contrato `salida`.

    Pide generación restringida por json_schema; si el servidor no lo
    soporta (4xx), reintenta en modo texto. En ambos casos la respuesta
    pasa por la validación Pydantic antes de devolverse.
    """
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
