"""Cliente LLM del agente conversacional: conecta el LLM con las tools.

Este módulo es la pieza que une el LLM (Z.ai / GLM, compatible con el protocolo
de OpenAI) con las cinco tools de solo lectura de :mod:`src.agente.tools`. Su
única función pública es :func:`preguntar`, que implementa el **bucle de
function calling**: enviar la pregunta al LLM, ejecutar las tools que pida,
devolver sus resultados al LLM y repetir hasta que el modelo dé una respuesta
final en texto.

Flujo de :func:`preguntar`
--------------------------
1. Se construye la lista de mensajes: ``system`` (con :data:`SYSTEM_PROMPT`),
   el historial previo (si lo hay) y el mensaje ``user`` con la pregunta.
2. Se llama a ``client.chat.completions.create(..., tools=TOOLS_SCHEMA)``.
3. Según el ``finish_reason`` de la respuesta:

   * ``tool_calls``: se ejecutan las tools solicitadas, se añade el mensaje
     ``assistant`` (con sus ``tool_calls``) y un mensaje ``tool`` por cada
     resultado, y se repite desde el paso 2.
   * ``stop``: se devuelve el texto del modelo como respuesta final.
   * cualquier otro: se trata como error (:class:`RuntimeError`).

El cliente LLM y el cliente de Supabase
---------------------------------------
* El cliente LLM se crea con ``OpenAI(api_key=..., base_url=...)`` a partir de
  ``LLM_API_KEY`` y ``LLM_BASE_URL``; el modelo se lee de ``LLM_MODEL``.
* Las tools reciben un ``supabase_client`` que **no** viene de la pregunta ni del
  historial: lo crea este módulo con ``SUPABASE_URL`` y ``SUPABASE_ANON_KEY``. Se
  usa la ``anon key`` porque el agente es de **solo lectura** (es la misma clave
  que usa el frontend; ver ``scripts/verificar_rls.py``). El cliente se crea de
  forma **perezosa**: solo la primera vez que hace falta ejecutar una tool, para
  que una pregunta que no toca datos (p. ej. un saludo) no dependa de Supabase.

Límite de iteraciones
---------------------
El bucle permite como mucho :data:`MAX_ITERACIONES` llamadas al LLM. Si el
modelo no llega a una respuesta final en ese margen, se lanza
:class:`RuntimeError` (evita bucles infinitos si el modelo insiste en llamar
tools).

Manejo de errores del LLM
-------------------------
* **Recuperables** (``429``, ``5xx``, timeouts y errores de conexión): se
  reintenta hasta :data:`MAX_INTENTOS` veces con *backoff* exponencial
  (``2 ** intento`` segundos: 1, 2, 4...). Si se agotan, se lanza
  :class:`RuntimeError`.
* **No recuperables** (``401``, ``400`` y demás ``4xx``): se propagan de
  inmediato, sin reintentar.
* **Tool inexistente**: no se aborta el bucle; se devuelve al LLM un mensaje
  ``tool`` con el error para que reaccione (p. ej. reintente con otra tool).
* **Argumentos inválidos o de negocio** (JSON mal formado, o ``ValueError``/
  ``TypeError`` de la tool): igual que el caso anterior, se devuelven al LLM como
  error del ``tool`` en lugar de cortar la conversación. El resto de excepciones
  (por ejemplo, un fallo de Supabase) **sí** se propagan.

Contrato de errores
-------------------
* :func:`preguntar`: :class:`RuntimeError` si el LLM falla de forma repetida,
  si se supera :data:`MAX_ITERACIONES` o si el ``finish_reason`` es inesperado.
* :func:`preguntar`: propaga tal cual las excepciones no recuperables del LLM
  (``401``, ``400``...).

Sin efectos secundarios al importar
-----------------------------------
Importar el módulo no se conecta a nada: el ``.env`` se carga de forma perezosa
(al llamar a :func:`preguntar`) y ``supabase`` se importa dentro de la función
que lo necesita. Solo se importa ``openai`` a nivel de módulo.
"""

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI

from src.agente.tools import (
    buscar_recomendaciones,
    comparar_proveedores,
    detalle_recomendacion,
    explicar_criterio,
    resumen_prioridad_ABC_XYZ,
)
from src.agente.tools_schema import TOOLS_SCHEMA

if TYPE_CHECKING:  # pragma: no cover - solo para las anotaciones de tipo
    # El cliente se importa solo para el chequeo de tipos: así el módulo (y sus
    # tests) no dependen del paquete 'supabase' en tiempo de ejecución.
    from supabase import Client

__all__ = ["SYSTEM_PROMPT", "TOOLS_DISPONIBLES", "preguntar"]

# ===================================================================== prompt

#: Prompt del sistema. Fija las reglas del agente: responder **solo** con datos
#: que provengan de las tools, no inventar, no modificar nada (solo lectura),
#: decir explícitamente cuándo no hay datos y responder siempre en español.
SYSTEM_PROMPT: str = """Eres un analista de compras experto que asiste a compradores en un sistema de optimización de compras.

REGLAS ESTRICTAS:

1. SOLO responde con información que provenga del resultado de las tools. NO inventes datos, NO supongas valores, NO uses conocimiento externo.

2. Si las tools no devuelven datos suficientes para responder, dilo EXPLÍCITAMENTE. Ejemplos:
   - "No hay recomendaciones registradas."
   - "No encontré información sobre el producto X."
   - "No tengo datos para responder esa pregunta."

3. Nunca modifiques datos. Eres una interfaz de SOLO LECTURA.

4. Cita datos concretos en tus respuestas (nombres, valores, estados).

5. Si el usuario pregunta algo fuera del alcance del sistema, acláralo amablemente.

6. Si el usuario pregunta algo con una temática ajena al sistema, por ejemplo recetas de cocina o consejos de vida, aclara amablemente que no puedes responder a eso.

7. Cuando menciones valores monetarios, usa el símbolo `$` (pesos mexicanos). Mantén el formato de números español (punto para miles, coma para decimales). Ejemplo: `$1.470,64`.

8. Responde en español, de forma clara y concisa."""

# =================================================================== límites

#: Máximo de llamadas al LLM dentro de un mismo :func:`preguntar` (el modelo
#: puede pedir varias rondas de tools antes de dar la respuesta final).
MAX_ITERACIONES: int = 5

#: Máximo de intentos de una misma llamada al LLM cuando el error es recuperable.
MAX_INTENTOS: int = 3

#: Códigos HTTP del LLM que se consideran recuperables (se reintentan).
CODIGOS_RECUPERABLES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

#: Ruta del ``.env`` de la raíz del proyecto, derivada de ``__file__``. El
#: módulo vive en ``backend/src/agente/``, así que la raíz son cuatro niveles
#: arriba (agente -> src -> backend -> raíz).
RUTA_ENV: Path = Path(__file__).resolve().parents[3] / ".env"

#: Mapa nombre-de-tool -> función Python, usado para ejecutar lo que pide el LLM.
TOOLS_DISPONIBLES: dict[str, Callable[..., object]] = {
    "buscar_recomendaciones": buscar_recomendaciones,
    "detalle_recomendacion": detalle_recomendacion,
    "explicar_criterio": explicar_criterio,
    "comparar_proveedores": comparar_proveedores,
    "resumen_prioridad_ABC_XYZ": resumen_prioridad_ABC_XYZ,
}

# --------------------------------------------------- estado de carga del .env

# Bandera para no releer el ``.env`` en cada llamada (``load_dotenv`` no pisa
# variables ya definidas, pero evita E/S repetida). No se evalúa al importar.
_ENTORNO_CARGADO: bool = False


def _cargar_entorno() -> None:
    """Carga las variables de ``.env`` (raíz del proyecto) una sola vez.

    ``load_dotenv`` no sobrescribe variables ya presentes en el entorno, así que
    se puede llamar sin miedo. Es perezoso: no se ejecuta al importar el módulo.
    """
    global _ENTORNO_CARGADO
    if _ENTORNO_CARGADO:
        return
    load_dotenv(RUTA_ENV)
    _ENTORNO_CARGADO = True


# ================================================================== clientes


def _crear_cliente_llm() -> OpenAI:
    """Crea el cliente del LLM a partir de ``LLM_API_KEY`` y ``LLM_BASE_URL``.

    Returns:
        Cliente ``OpenAI`` configurado contra el ``base_url`` del proveedor
        (Z.ai / GLM).

    Raises:
        RuntimeError: si falta alguna de las dos variables en el entorno.
    """
    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL")
    if not api_key or not base_url:
        raise RuntimeError(
            "Faltan LLM_API_KEY o LLM_BASE_URL en el entorno: no se puede crear "
            "el cliente del LLM."
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _leer_modelo() -> str:
    """Devuelve el modelo a usar, leído de ``LLM_MODEL``.

    Returns:
        El nombre del modelo configurado.

    Raises:
        RuntimeError: si ``LLM_MODEL`` no está definido o está vacío.
    """
    modelo = os.environ.get("LLM_MODEL")
    if not modelo:
        raise RuntimeError(
            "Falta LLM_MODEL en el entorno: no se sabe qué modelo del LLM usar."
        )
    return modelo


def _crear_supabase_client() -> "Client":
    """Crea un cliente de Supabase de solo lectura (``anon key``).

    Es la clave que corresponde al agente: solo lectura, igual que el frontend
    (ver ``scripts/verificar_rls.py``). El import de ``supabase`` es diferido
    para no depender del paquete al importar este módulo.

    Returns:
        Cliente de Supabase.

    Raises:
        RuntimeError: si faltan ``SUPABASE_URL`` o ``SUPABASE_ANON_KEY``.
    """
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_ANON_KEY en el entorno: no se puede "
            "crear el cliente de Supabase."
        )
    return create_client(url, anon_key)


# ==================================================================== bucle


def preguntar(
    pregunta: str,
    historial: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Envía una pregunta al LLM y devuelve la respuesta (con función calling).

    Ejecuta el bucle de *function calling*: manda la pregunta al LLM con las
    tools disponibles, ejecuta las que solicite, le devuelve sus resultados y
    repite hasta obtener una respuesta final en texto.

    Args:
        pregunta: la pregunta del usuario.
        historial: historial previo de la conversación (**sin** el prompt del
            sistema). Si es ``None``, empieza una conversación nueva. No se
            modifica la lista recibida.

    Returns:
        Tupla ``(respuesta_texto, historial_actualizado)``. El
        ``historial_actualizado`` incluye los mensajes ``user``, ``assistant`` y
        ``tool`` de esta interacción (más los previos, si los había) y **no**
        incluye el prompt del sistema: se pasa tal cual en la próxima llamada.

    Raises:
        RuntimeError: si el LLM falla de forma repetida (error recuperable
            agotado), si se supera :data:`MAX_ITERACIONES` o si el
            ``finish_reason`` es inesperado.
        Exception: propaga tal cual los errores **no** recuperables del LLM
            (p. ej. ``401`` o ``400``).
    """
    _cargar_entorno()
    cliente_llm = _crear_cliente_llm()
    modelo = _leer_modelo()

    mensajes: list[dict] = _construir_mensajes(pregunta, historial)
    supabase_client: "Client | None" = None

    for _ in range(MAX_ITERACIONES):
        eleccion = _completar_con_reintentos(cliente_llm, modelo, mensajes).choices[0]
        mensaje = eleccion.message

        if eleccion.finish_reason == "tool_calls":
            mensajes.append(_mensaje_asistente(mensaje))
            if supabase_client is None:
                supabase_client = _crear_supabase_client()
            for llamada in mensaje.tool_calls or []:
                mensajes.append(_ejecutar_tool(llamada, supabase_client))
            continue

        if eleccion.finish_reason == "stop":
            mensajes.append(_mensaje_asistente(mensaje))
            return mensaje.content or "", mensajes[1:]

        raise RuntimeError(
            "El LLM terminó con un estado inesperado: "
            f"{eleccion.finish_reason!r}."
        )

    raise RuntimeError(
        f"Se superó el límite de {MAX_ITERACIONES} iteraciones de uso de tools "
        "sin obtener una respuesta final."
    )


def _construir_mensajes(
    pregunta: str,
    historial: list[dict] | None,
) -> list[dict]:
    """Arma la lista de mensajes que se envía al LLM.

    Args:
        pregunta: la pregunta del usuario.
        historial: historial previo (sin el prompt del sistema), o ``None``.

    Returns:
        Lista nueva de mensajes: ``system`` + historial previo (si lo hay) +
        ``user``. No modifica el historial recibido.
    """
    mensajes: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if historial:
        mensajes.extend(historial)
    mensajes.append({"role": "user", "content": pregunta})
    return mensajes


def _completar_con_reintentos(
    cliente_llm: OpenAI,
    modelo: str,
    mensajes: list[dict],
) -> object:
    """Llama al LLM reintentando solo los errores recuperables.

    Reintenta hasta :data:`MAX_INTENTOS` veces con *backoff* exponencial
    (``2 ** intento`` segundos) cuando el error es recuperable (``429``, ``5xx``,
    *timeouts* o fallos de conexión). Un error no recuperable (``401``, ``400``...)
    se propaga de inmediato.

    Args:
        cliente_llm: cliente del LLM ya configurado.
        modelo: nombre del modelo a usar.
        mensajes: mensajes de la conversación.

    Returns:
        La respuesta del LLM (``ChatCompletion``).

    Raises:
        RuntimeError: si se agotan los intentos con errores recuperables.
        Exception: el error no recuperable original, propagado tal cual.
    """
    ultimo_error: Exception | None = None
    for intento in range(MAX_INTENTOS):
        try:
            return cliente_llm.chat.completions.create(
                model=modelo,
                messages=mensajes,
                tools=TOOLS_SCHEMA,
            )
        except Exception as error:  # noqa: BLE001 - se clasifica justo debajo
            if not _es_error_recuperable(error):
                raise
            ultimo_error = error
            if intento < MAX_INTENTOS - 1:
                time.sleep(2 ** intento)
    raise RuntimeError(
        f"El LLM falló repetidamente tras {MAX_INTENTOS} intentos: {ultimo_error}"
    ) from ultimo_error


def _es_error_recuperable(error: Exception) -> bool:
    """Indica si un error del LLM conviene reintentarse.

    Se consideran recuperables los *timeouts*, los fallos de conexión y los
    errores con un código HTTP en :data:`CODIGOS_RECUPERABLES` (``429``, ``5xx``).

    Args:
        error: excepción lanzada por el cliente LLM.

    Returns:
        ``True`` si merece la pena reintentar, ``False`` en caso contrario.
    """
    if isinstance(
        error, (APITimeoutError, APIConnectionError, TimeoutError, ConnectionError)
    ):
        return True
    return getattr(error, "status_code", None) in CODIGOS_RECUPERABLES


def _mensaje_asistente(mensaje: object) -> dict:
    """Convierte el mensaje ``assistant`` del SDK a un dict plano.

    El resultado se guarda en el historial, así que se normaliza a tipos nativos
    (dicts/strings) en lugar de conservar los objetos del SDK.

    Args:
        mensaje: ``message`` de la respuesta del LLM.

    Returns:
        Dict con ``role="assistant"``, su ``content`` y, si los hubiera, sus
        ``tool_calls``.
    """
    resultado: dict = {
        "role": "assistant",
        "content": getattr(mensaje, "content", None),
    }
    tool_calls = getattr(mensaje, "tool_calls", None)
    if tool_calls:
        resultado["tool_calls"] = [
            {
                "id": llamada.id,
                "type": "function",
                "function": {
                    "name": llamada.function.name,
                    "arguments": llamada.function.arguments,
                },
            }
            for llamada in tool_calls
        ]
    return resultado


def _ejecutar_tool(llamada: object, supabase_client: "Client") -> dict:
    """Ejecuta una tool pedida por el LLM y devuelve el mensaje ``tool``.

    Nunca lanza por problemas atribuibles al LLM (tool inexistente, argumentos
    mal formados o rechazados por la tool): en esos casos devuelve un mensaje
    ``tool`` con un ``{"error": ...}`` para que el modelo reaccione. Un fallo
    ajeno a esos casos (p. ej. de Supabase) sí se propaga.

    Args:
        llamada: ``tool_call`` de la respuesta del LLM.
        supabase_client: cliente de Supabase (solo lectura) que reciben las tools.

    Returns:
        Dict ``{"role": "tool", "tool_call_id": ..., "content": <json>}``.
    """
    nombre = llamada.function.name
    funcion = TOOLS_DISPONIBLES.get(nombre)
    if funcion is None:
        return _mensaje_tool(llamada.id, {"error": f"Tool desconocida: '{nombre}'."})

    try:
        argumentos = json.loads(llamada.function.arguments or "{}")
        resultado = funcion(supabase_client, **argumentos)
    except json.JSONDecodeError as error:
        return _mensaje_tool(
            llamada.id, {"error": f"Argumentos JSON inválidos: {error}."}
        )
    except (TypeError, ValueError) as error:
        return _mensaje_tool(llamada.id, {"error": str(error)})

    return _mensaje_tool(llamada.id, resultado)


def _mensaje_tool(id_llamada: str, resultado: object) -> dict:
    """Serializa el resultado de una tool al mensaje ``tool`` del protocolo.

    Args:
        id_llamada: ``id`` del ``tool_call`` al que responde.
        resultado: resultado de la tool (o un dict ``{"error": ...}``).

    Returns:
        Dict con ``role="tool"`` y el resultado serializado a JSON. ``default=str``
        cubre valores no serializables por sí solos (p. ej. ``Decimal``).
    """
    return {
        "role": "tool",
        "tool_call_id": id_llamada,
        "content": json.dumps(resultado, ensure_ascii=False, default=str),
    }
