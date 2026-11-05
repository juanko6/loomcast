import json

import httpx
import pytest
from pydantic import BaseModel

from backend import parada
from backend.clients import llm


class Salida(BaseModel):
    titulo: str
    n: int = 0


def _sse(*trozos: str, fin: str = "stop") -> httpx.Response:
    """La respuesta tal como la manda el servidor: SSE, un `data:` por trozo.

    El cliente pide `stream: true` para poder parar entre trozos (ver
    `llm._completar`), así que los dobles tienen que hablar ese formato.
    """
    lineas = [
        "data: " + json.dumps({"choices": [{"delta": {"content": x}}]}) for x in trozos
    ]
    lineas.append("data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": fin}]}))
    # El trozo final de recuento que mandan algunos servidores, sin `choices`.
    lineas.append("data: " + json.dumps({"choices": [], "usage": {"total_tokens": 9}}))
    lineas.append("data: [DONE]")
    return httpx.Response(200, text="\n\n".join(lineas) + "\n\n",
                          headers={"content-type": "text/event-stream"})


def _respuesta(contenido: str) -> httpx.Response:
    # Troceado como lo trocearía el modelo, para que se note que se junta bien.
    mitad = len(contenido) // 2
    return _sse(contenido[:mitad], contenido[mitad:])


def _cortada(contenido: str) -> httpx.Response:
    """Lo que devuelve el servidor cuando se agotan los max_tokens."""
    return _sse(contenido, fin="length")


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


def test_extract_json_une_el_guion_partido_en_cadenas_sueltas():
    """El Qwen de MLX escribe cada marcador como una cadena aparte y se come la coma final."""
    texto = (
        '{\n"tags": "jazz noir, tenor sax",\n'
        '"lyrics": "[Intro - piano alone]",\n'
        '"[Theme A - sax states the melody, bass walks]",\n'
        '"[Outro - fades to silence]"\n'
        '"bpm": 78,\n"keyscale": "D minor"\n}'
    )
    assert llm._extract_json(texto) == {
        "tags": "jazz noir, tenor sax",
        "lyrics": "[Intro - piano alone]\n[Theme A - sax states the melody, bass walks]\n"
                  "[Outro - fades to silence]",
        "bpm": 78,
        "keyscale": "D minor",
    }


def test_extract_json_pone_la_coma_que_falta_antes_de_la_clave():
    texto = '{\n"lyrics": "[Intro]\\n[Outro]"\n"bpm": 115\n"timesig": "4"\n}'
    assert llm._extract_json(texto) == {"lyrics": "[Intro]\n[Outro]", "bpm": 115, "timesig": "4"}


def test_extract_json_no_toca_un_json_valido_con_comas_y_saltos_dentro():
    datos = {"tags": 'una frase, "otra",\n"y más"', "bpm": 90}
    assert llm._extract_json(json.dumps(datos, indent=1)) == datos


# --- chat -------------------------------------------------------------------

def test_chat_pide_streaming_para_poder_pararse(http_mock):
    """Sin streaming, el hilo de la cola se queda bloqueado hasta que el modelo
    termina y pulsar "Parar" no lo toca."""
    vistas = http_mock(lambda r: _respuesta('{"titulo": "hola"}'))

    llm.chat("sys", "usr", Salida)

    assert json.loads(vistas[0].content)["stream"] is True


def test_chat_abandona_la_generacion_si_se_pide_parar(http_mock, parada_pedida):
    """Se corta entre trozos y se cierra la conexión, para que el servidor
    abandone la generación en vez de seguir ocupando el modelo."""
    vistas = http_mock(lambda r: _respuesta('{"titulo": "un guion larguísimo"}'))

    with pytest.raises(parada.Parado, match="generando texto"):
        llm.chat("s", "u", Salida)

    assert len(vistas) == 1      # y no se reintenta sin schema


def test_chat_un_trozo_que_no_es_json_se_dice_claro(http_mock):
    http_mock(lambda r: httpx.Response(
        200, text="data: esto no es json\n\n",
        headers={"content-type": "text/event-stream"},
    ))

    with pytest.raises(llm.LLMError, match="no es JSON"):
        llm.chat("s", "u", Salida)


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
