"""Cliente para llama-server (API OpenAI-compatible) con salida JSON estructurada."""
import json
import re

import httpx

from ..config import LLM_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT_S, LLM_URL


class LLMError(RuntimeError):
    pass


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


def chat_json(system: str, user: str, schema: dict | None = None) -> dict | list:
    """Chat completion pidiendo JSON. Usa json_schema si llama-server lo soporta;
    si responde 4xx, reintenta en modo texto y parsea."""
    base = {
        "model": LLM_MODEL,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": 4096,
        # Las etapas del pipeline no necesitan modo razonamiento (Qwen3/3.6):
        # sin esto el modelo "piensa" miles de tokens antes del JSON.
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    with httpx.Client(timeout=LLM_TIMEOUT_S) as client:
        if schema is not None:
            body = base | {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "salida", "schema": schema, "strict": True},
                }
            }
            r = client.post(f"{LLM_URL}/v1/chat/completions", json=body)
            if r.status_code < 400:
                return _extract_json(r.json()["choices"][0]["message"]["content"])

        r = client.post(f"{LLM_URL}/v1/chat/completions", json=base)
        if r.status_code >= 400:
            raise LLMError(f"llama-server respondió {r.status_code}: {r.text[:300]}")
        return _extract_json(r.json()["choices"][0]["message"]["content"])


def ping() -> bool:
    try:
        with httpx.Client(timeout=3) as client:
            return client.get(f"{LLM_URL}/v1/models").status_code < 400
    except httpx.HTTPError:
        return False
