"""Tests unitarios del cliente LLM del agente (function calling con Z.ai/GLM).

Se prueba :func:`src.agente.llm_client.preguntar` con un cliente de OpenAI
**falso**: no se llama a Z.ai ni a la red. También se sustituyen el cliente de
Supabase, la carga del ``.env`` y ``time.sleep`` para que las pruebas sean
herméticas y rápidas.

El cliente falso devuelve "eventos" en orden: cada evento es o una respuesta
simulada (con o sin ``tool_calls``) o una excepción a lanzar. Así se reproduce
tanto el bucle normal como los reintentos y los errores.

Las tools Python se sustituyen por ``Mock`` para poder afirmar que el bucle las
ejecuta con el ``supabase_client`` inyectado y con los argumentos del LLM.
"""

import json
from unittest.mock import Mock

import pytest

from src.agente import llm_client
from src.agente.llm_client import (
    MAX_INTENTOS,
    MAX_ITERACIONES,
    SYSTEM_PROMPT,
    TOOLS_SCHEMA,
    preguntar,
)

# --------------------------------------------------------------- dobles falsos


class _ErrorLLM(Exception):
    """Excepción de prueba con ``status_code``, como las del SDK de OpenAI."""

    def __init__(self, status_code: int, mensaje: str = "error") -> None:
        super().__init__(f"{status_code}: {mensaje}")
        self.status_code = status_code


class _FuncionLlamada:
    """``function`` de un ``tool_call`` falso."""

    def __init__(self, nombre: str, argumentos: str) -> None:
        self.name = nombre
        self.arguments = argumentos


class _LlamadaFalsa:
    """``tool_call`` falso."""

    def __init__(self, id_: str, nombre: str, argumentos: str) -> None:
        self.id = id_
        self.type = "function"
        self.function = _FuncionLlamada(nombre, argumentos)


class _MensajeFalso:
    """``message`` falso de una respuesta del LLM."""

    def __init__(self, content=None, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _EleccionFalsa:
    """``choice`` falso: mensaje + ``finish_reason``."""

    def __init__(self, mensaje: _MensajeFalso, finish_reason: str) -> None:
        self.message = mensaje
        self.finish_reason = finish_reason


class _RespuestaFalsa:
    """``ChatCompletion`` falso con una sola elección."""

    def __init__(self, finish_reason: str, content=None, tool_calls=None) -> None:
        mensaje = _MensajeFalso(content, tool_calls)
        self.choices = [_EleccionFalsa(mensaje, finish_reason)]


class _ClienteLLMFalso:
    """Cliente de OpenAI falso expuesto como ``chat.completions.create``.

    Se le pasa una lista de eventos; cada llamada a ``create`` consume el
    siguiente: si es una excepción la lanza, si no, la devuelve. Registra cada
    llamada (``model``, ``messages`` y ``tools``) para poder inspeccionarla.
    """

    def __init__(self, eventos: list) -> None:
        self._eventos = list(eventos)
        self.llamadas: list[dict] = []
        # ``create`` cuelga de ``chat.completions``; se apunta a sí mismo.
        self.chat = self
        self.completions = self

    def create(self, *, model, messages, tools):
        """Registra la llamada (copia de los mensajes) y devuelve el evento.

        Se guarda una **copia** de ``messages`` para reflejar lo que el modelo ve
        en ese instante: ``preguntar`` sigue añadiendo mensajes a su lista tras
        cada llamada, y sin la copia esas mutaciones se verían en lo registrado.
        """
        self.llamadas.append(
            {"model": model, "messages": list(messages), "tools": tools}
        )
        evento = self._eventos.pop(0)
        if isinstance(evento, BaseException):
            raise evento
        return evento


# ------------------------------------------------------------------ utilidades


def _respuesta_texto(texto: str) -> _RespuestaFalsa:
    """Respuesta final del LLM (``finish_reason="stop"``)."""
    return _RespuestaFalsa("stop", content=texto)


def _respuesta_tools(*llamadas: _LlamadaFalsa) -> _RespuestaFalsa:
    """Respuesta del LLM que pide ejecutar tools (``finish_reason="tool_calls"``)."""
    return _RespuestaFalsa("tool_calls", content=None, tool_calls=list(llamadas))


def _llamada(id_: str, nombre: str, **argumentos) -> _LlamadaFalsa:
    """``tool_call`` con sus argumentos ya serializados a JSON."""
    return _LlamadaFalsa(id_, nombre, json.dumps(argumentos))


def _preparar(
    monkeypatch: pytest.MonkeyPatch,
    eventos: list,
    *,
    herramientas: dict | None = None,
    supabase: object = None,
) -> _ClienteLLMFalso:
    """Sustituye las dependencias externas de ``llm_client`` para el test.

    Devuelve el cliente LLM falso para poder inspeccionar sus llamadas. El
    ``supabase_client`` que reciben las tools se controla con ``supabase``.
    """
    cliente = _ClienteLLMFalso(eventos)
    sentinela = object() if supabase is None else supabase
    monkeypatch.setattr(llm_client, "_cargar_entorno", lambda: None)
    monkeypatch.setattr(llm_client, "_crear_cliente_llm", lambda: cliente)
    monkeypatch.setattr(llm_client, "_leer_modelo", lambda: "modelo-de-prueba")
    monkeypatch.setattr(llm_client, "_crear_supabase_client", lambda: sentinela)
    monkeypatch.setattr(llm_client.time, "sleep", lambda _segundos: None)
    if herramientas is not None:
        monkeypatch.setattr(llm_client, "TOOLS_DISPONIBLES", herramientas)
    return cliente


# ====================================================== pregunta sin tools


def test_pregunta_simple_sin_tool_calls_devuelve_texto(monkeypatch):
    """Sin ``tool_calls`` el bucle llama una vez y devuelve el texto."""
    cliente = _preparar(monkeypatch, [_respuesta_texto("Hola, ¿qué necesitás?")])

    respuesta, historial = preguntar("Hola")

    assert respuesta == "Hola, ¿qué necesitás?"
    assert historial == [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola, ¿qué necesitás?"},
    ]
    assert len(cliente.llamadas) == 1
    llamada = cliente.llamadas[0]
    assert llamada["model"] == "modelo-de-prueba"
    assert llamada["tools"] == TOOLS_SCHEMA
    assert llamada["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert llamada["messages"][1] == {"role": "user", "content": "Hola"}


def test_historial_none_empieza_conversacion_nueva(monkeypatch):
    """Sin historial, la conversación arranca con system + user."""
    cliente = _preparar(monkeypatch, [_respuesta_texto("Ok")])

    _, historial = preguntar("Hola", historial=None)

    assert [m["role"] for m in historial] == ["user", "assistant"]
    assert cliente.llamadas[0]["messages"][0]["role"] == "system"
    assert len(cliente.llamadas[0]["messages"]) == 2


# ====================================================== ejecución de tools


def test_una_tool_call_ejecuta_la_tool_y_arma_el_historial(monkeypatch):
    """Una ``tool_call`` se ejecuta y su resultado entra al historial."""
    herramienta = Mock(return_value=[{"producto_nombre": "Producto A"}])
    cliente_supabase = object()
    cliente = _preparar(
        monkeypatch,
        [
            _respuesta_tools(
                _llamada("call-1", "buscar_recomendaciones", urgencia="Crítico")
            ),
            _respuesta_texto("Hay 1 recomendación crítica."),
        ],
        herramientas={"buscar_recomendaciones": herramienta},
        supabase=cliente_supabase,
    )

    respuesta, historial = preguntar("¿Qué es urgente?")

    assert respuesta == "Hay 1 recomendación crítica."
    # La tool recibe el supabase_client inyectado y los argumentos del LLM.
    herramienta.assert_called_once_with(cliente_supabase, urgencia="Crítico")

    # assistant (con tool_calls) + tool + assistant final.
    assert historial[1]["role"] == "assistant"
    assert historial[1]["tool_calls"][0]["id"] == "call-1"
    assert historial[1]["tool_calls"][0]["function"]["name"] == "buscar_recomendaciones"
    mensaje_tool = historial[2]
    assert mensaje_tool["role"] == "tool"
    assert mensaje_tool["tool_call_id"] == "call-1"
    assert json.loads(mensaje_tool["content"]) == [{"producto_nombre": "Producto A"}]
    assert historial[3] == {
        "role": "assistant",
        "content": "Hay 1 recomendación crítica.",
    }
    assert len(cliente.llamadas) == 2


def test_dos_tool_calls_en_una_respuesta_ejecuta_ambas(monkeypatch):
    """Dos ``tool_calls`` en la misma respuesta se ejecutan las dos."""
    primera = Mock(return_value=[{"x": 1}])
    segunda = Mock(return_value={"y": 2})
    _preparar(
        monkeypatch,
        [
            _respuesta_tools(
                _llamada("c1", "buscar_recomendaciones"),
                _llamada("c2", "resumen_prioridad_ABC_XYZ"),
            ),
            _respuesta_texto("Listo."),
        ],
        herramientas={
            "buscar_recomendaciones": primera,
            "resumen_prioridad_ABC_XYZ": segunda,
        },
    )

    respuesta, historial = preguntar("Dame todo")

    assert respuesta == "Listo."
    primera.assert_called_once()
    segunda.assert_called_once()
    assert [m["role"] for m in historial] == ["user", "assistant", "tool", "tool", "assistant"]
    assert historial[2]["tool_call_id"] == "c1"
    assert historial[3]["tool_call_id"] == "c2"


def test_multiples_iteraciones_hasta_la_respuesta_final(monkeypatch):
    """tool_call -> resultado -> tool_call -> resultado -> texto."""
    herramienta = Mock(side_effect=[[{"a": 1}], {"b": 2}])
    cliente = _preparar(
        monkeypatch,
        [
            _respuesta_tools(_llamada("c1", "buscar_recomendaciones")),
            _respuesta_tools(_llamada("c2", "buscar_recomendaciones")),
            _respuesta_texto("Final."),
        ],
        herramientas={"buscar_recomendaciones": herramienta},
    )

    respuesta, historial = preguntar("Iterá")

    assert respuesta == "Final."
    assert herramienta.call_count == 2
    assert len(cliente.llamadas) == 3
    assert [m["role"] for m in historial] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]


# ====================================================== errores y reintentos


def test_error_429_reintenta_con_backoff_y_luego_responde(monkeypatch):
    """Un 429 se reintenta (con ``2 ** intento``) y, si luego va, responde."""
    cliente = _preparar(
        monkeypatch,
        [_ErrorLLM(429, "rate limit"), _respuesta_texto("Ok")],
    )
    esperas: list[float] = []
    monkeypatch.setattr(llm_client.time, "sleep", esperas.append)

    respuesta, _ = preguntar("Hola")

    assert respuesta == "Ok"
    assert len(cliente.llamadas) == 2
    assert esperas == [1]  # 2 ** 0


def test_error_429_persistente_lanza_runtime_error(monkeypatch):
    """Si todos los intentos fallan con 429, se lanza ``RuntimeError``."""
    cliente = _preparar(
        monkeypatch,
        [_ErrorLLM(429) for _ in range(MAX_INTENTOS)],
    )

    with pytest.raises(RuntimeError, match="repetidamente"):
        preguntar("Hola")

    assert len(cliente.llamadas) == MAX_INTENTOS


def test_error_401_lanza_inmediatamente_sin_reintentar(monkeypatch):
    """Un 401 se propaga tal cual y no se reintenta."""
    error = _ErrorLLM(401, "unauthorized")
    cliente = _preparar(monkeypatch, [error])

    with pytest.raises(_ErrorLLM) as capturado:
        preguntar("Hola")

    assert capturado.value is error
    assert len(cliente.llamadas) == 1


def test_error_400_lanza_inmediatamente_sin_reintentar(monkeypatch):
    """Un 400 también se propaga de inmediato."""
    error = _ErrorLLM(400, "bad request")
    cliente = _preparar(monkeypatch, [error])

    with pytest.raises(_ErrorLLM):
        preguntar("Hola")

    assert len(cliente.llamadas) == 1


def test_supera_el_limite_de_iteraciones_lanza_runtime_error(monkeypatch):
    """Si el LLM nunca deja de pedir tools, se supera MAX_ITERACIONES."""
    herramienta = Mock(return_value=[])
    cliente = _preparar(
        monkeypatch,
        [
            _respuesta_tools(_llamada(f"c{i}", "buscar_recomendaciones"))
            for i in range(MAX_ITERACIONES)
        ],
        herramientas={"buscar_recomendaciones": herramienta},
    )

    with pytest.raises(RuntimeError, match="iteraciones"):
        preguntar("Loop")

    assert len(cliente.llamadas) == MAX_ITERACIONES
    assert herramienta.call_count == MAX_ITERACIONES


def test_finish_reason_inesperado_lanza_runtime_error(monkeypatch):
    """Un ``finish_reason`` distinto de stop/tool_calls es un error."""
    _preparar(monkeypatch, [_RespuestaFalsa("length", content="cortado")])

    with pytest.raises(RuntimeError, match="inesperado"):
        preguntar("Hola")


# ============================================== tools problemáticas (seguir)


def test_tool_inexistente_anade_mensaje_de_error_y_continua(monkeypatch):
    """Una tool desconocida no corta el bucle: se informa y se sigue."""
    _preparar(
        monkeypatch,
        [
            _respuesta_tools(_llamada("c1", "tool_que_no_existe")),
            _respuesta_texto("Sigo con otra cosa."),
        ],
        herramientas={},
    )

    respuesta, historial = preguntar("Hola")

    assert respuesta == "Sigo con otra cosa."
    mensaje_tool = historial[2]
    assert mensaje_tool["role"] == "tool"
    assert mensaje_tool["tool_call_id"] == "c1"
    assert "error" in json.loads(mensaje_tool["content"])


def test_argumentos_json_invalidos_anaden_error_y_continua(monkeypatch):
    """Argumentos que no son JSON válido se reportan y el bucle continúa."""
    herramienta = Mock()
    _preparar(
        monkeypatch,
        [
            _respuesta_tools(
                _LlamadaFalsa("c1", "buscar_recomendaciones", "{no-es-json")
            ),
            _respuesta_texto("Sigo."),
        ],
        herramientas={"buscar_recomendaciones": herramienta},
    )

    respuesta, historial = preguntar("Hola")

    assert respuesta == "Sigo."
    assert "error" in json.loads(historial[2]["content"])
    herramienta.assert_not_called()


def test_tool_que_lanza_value_error_se_reporta_y_continua(monkeypatch):
    """Un ``ValueError`` de la tool se devuelve como error, no rompe el bucle."""
    herramienta = Mock(side_effect=ValueError("producto no válido"))
    _preparar(
        monkeypatch,
        [
            _respuesta_tools(
                _llamada("c1", "detalle_recomendacion", producto_nombre="X")
            ),
            _respuesta_texto("Sigo."),
        ],
        herramientas={"detalle_recomendacion": herramienta},
    )

    respuesta, historial = preguntar("Hola")

    assert respuesta == "Sigo."
    assert json.loads(historial[2]["content"]) == {"error": "producto no válido"}


# ====================================================== historial


def test_historial_previo_se_preserva_y_no_se_muta(monkeypatch):
    """El historial previo se conserva y la lista del llamador no se modifica."""
    previo = [
        {"role": "user", "content": "Pregunta 1"},
        {"role": "assistant", "content": "Respuesta 1"},
    ]
    copia = [dict(mensaje) for mensaje in previo]
    cliente = _preparar(monkeypatch, [_respuesta_texto("Respuesta 2")])

    _, historial = preguntar("Pregunta 2", historial=previo)

    # El historial devuelto empieza por los mensajes previos.
    assert historial[:2] == previo
    assert historial[2] == {"role": "user", "content": "Pregunta 2"}
    assert historial[3] == {"role": "assistant", "content": "Respuesta 2"}
    # El system prompt se antepone (una sola vez) sin duplicar el historial.
    mensajes = cliente.llamadas[0]["messages"]
    assert mensajes[0]["role"] == "system"
    assert mensajes[1] == previo[0]
    assert mensajes[2] == previo[1]
    # La lista del llamador quedó intacta.
    assert previo == copia


# ====================================================== configuración


def test_crear_cliente_llm_usa_el_entorno(monkeypatch):
    """``_crear_cliente_llm`` lee la API key y el base URL del entorno."""
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("LLM_BASE_URL", "https://ejemplo.test/v1/")
    mock_openai = Mock()
    monkeypatch.setattr(llm_client, "OpenAI", mock_openai)

    llm_client._crear_cliente_llm()

    mock_openai.assert_called_once_with(
        api_key="clave-de-prueba", base_url="https://ejemplo.test/v1/"
    )


def test_crear_cliente_llm_sin_entorno_lanza_runtime_error(monkeypatch):
    """Sin ``LLM_API_KEY``/``LLM_BASE_URL`` no se puede crear el cliente."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm_client._crear_cliente_llm()


def test_leer_modelo_sin_entorno_lanza_runtime_error(monkeypatch):
    """Sin ``LLM_MODEL`` no se sabe qué modelo usar."""
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        llm_client._leer_modelo()
