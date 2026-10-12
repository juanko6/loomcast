import json

import httpx
import pytest
from pydantic import BaseModel

from backend.clients import llm


class Salida(BaseModel):
    titulo: str
    n: int = 0


def _respuesta(contenido: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, json={"choices": [{"message": {"content": contenido}}]}
    )


def _cortada(contenido: str) -> httpx.Response:
    """Lo que devuelve el servidor cuando se agotan los max_tokens."""
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": contenido},
                           "finish_reason": "length"}]},
    )


# --- _extract_json ----------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ('{"a": 1}', {"a": 1}),
    ('  [1, 2]  ', [1, 2]),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('```\n{"a": 1}\n```', {"a": 1}),
    ('Claro, aquí tienes: {"a": 1} ¡Espero que sirva!', {"a": 1}),
    ('Resultado: [{"a": 1}, {"a": 2}] fin', [{"a": 1}, {"a": 2}]),
])
def test_extract_json_tolera_fences_y_texto_alrededor(texto, esperado):
    assert llm._extract_json(texto) == esperado


@pytest.mark.parametrize("texto", ["", "sin json por ningún lado", "{ roto"])
def test_extract_json_sin_json_valido_lanza_llmerror(texto):
    with pytest.raises(llm.LLMError):
        llm._extract_json(texto)


# --- chat -------------------------------------------------------------------

def test_chat_camino_feliz_valida_contra_el_esquema(http_mock):
    vistas = http_mock(lambda r: _respuesta('{"titulo": "hola", "n": 3}'))

    r = llm.chat("sys", "usr", Salida)

    assert r == Salida(titulo="hola", n=3)
    cuerpo = json.loads(vistas[0].content)
    assert cuerpo["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert cuerpo["response_format"]["json_schema"]["schema"] == Salida.model_json_schema()
    assert vistas[0].url.path == "/v1/chat/completions"


def test_chat_reintenta_sin_schema_si_el_servidor_lo_rechaza(http_mock):
    def handler(request):
        if "response_format" in json.loads(request.content):
            return httpx.Response(400, text="no soportado")
        return _respuesta('{"titulo": "ok"}')

    vistas = http_mock(handler)

    assert llm.chat("s", "u", Salida).titulo == "ok"
    assert len(vistas) == 2
    assert "response_format" not in json.loads(vistas[1].content)


def test_chat_respuesta_cortada_lo_dice_en_vez_de_culpar_al_json(http_mock):
    """Un guion que no cabe en max_tokens llega como JSON a medias. Sin mirar
    finish_reason el error sale como "JSON inválido" y parece que el modelo
    escribe mal, cuando lo que hay que tocar es max_tokens."""
    http_mock(lambda r: _cortada('{"titulo": "a med'))

    with pytest.raises(llm.LLMTruncado) as e:
        llm.chat("s", "u", Salida)

    assert "sin tokens" in str(e.value)
    assert "max_tokens" in str(e.value)
    assert "a med" in str(e.value)  # dice por dónde se quedó


def test_chat_no_reintenta_si_la_respuesta_vino_cortada(http_mock):
    """Reintentar sin schema daría el mismo corte y doblaría la espera."""
    vistas = http_mock(lambda r: _cortada('{"titulo": "a med'))

    with pytest.raises(llm.LLMTruncado):
        llm.chat("s", "u", Salida)

    assert len(vistas) == 1


def test_chat_error_en_ambos_intentos_lanza_llmerror(http_mock):
    http_mock(lambda r: httpx.Response(500, text="caído"))
    with pytest.raises(llm.LLMError, match="500"):
        llm.chat("s", "u", Salida)


def test_chat_salida_que_incumple_el_contrato(http_mock):
    http_mock(lambda r: _respuesta('{"n": 1}'))  # falta "titulo"
    with pytest.raises(llm.LLMError, match="contrato Salida"):
        llm.chat("s", "u", Salida)


def test_chat_contenido_vacio(http_mock):
    http_mock(lambda r: _respuesta(""))
    with pytest.raises(llm.LLMError):
        llm.chat("s", "u", Salida)


def test_chat_envia_temperature_y_template_kwargs_solo_si_estan_configurados(http_mock):
    from dataclasses import replace

    base = llm.activo()
    try:
        llm.configurar(replace(base, temperature=None, chat_template_kwargs={}))
        vistas = http_mock(lambda r: _respuesta('{"titulo": "x"}'))
        llm.chat("s", "u", Salida)
        cuerpo = json.loads(vistas[0].content)
        assert "temperature" not in cuerpo and "chat_template_kwargs" not in cuerpo

        llm.configurar(replace(base, temperature=0.2,
                               chat_template_kwargs={"enable_thinking": False}))
        llm.chat("s", "u", Salida)
        cuerpo = json.loads(vistas[1].content)
        assert cuerpo["temperature"] == 0.2
        assert cuerpo["chat_template_kwargs"] == {"enable_thinking": False}
    finally:
        llm.configurar(base)


# --- ping -------------------------------------------------------------------

def test_ping_responde(http_mock):
    vistas = http_mock(lambda r: httpx.Response(200, json={}))
    assert llm.ping("http://x:1") is True
    assert vistas[0].url == "http://x:1/v1/models"


def test_ping_servidor_con_error_http(http_mock):
    http_mock(lambda r: httpx.Response(503))
    assert llm.ping("http://x:1") is False


def test_ping_sin_conexion(http_mock):
    def handler(request):
        raise httpx.ConnectError("sin red")

    http_mock(handler)
    assert llm.ping("http://x:1") is False
