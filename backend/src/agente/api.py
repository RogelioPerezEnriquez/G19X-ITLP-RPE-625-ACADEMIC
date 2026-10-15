"""API HTTP del agente conversacional.

Expone el agente (implementado en :mod:`src.agente.llm_client`) a través de un
endpoint HTTP para que el frontend pueda consultarlo.

Uso:
    uvicorn src.agente.api:app --reload --port 8000

Desde la raíz del proyecto también se puede levantar con::

    python scripts/run_api.py

Endpoints
---------
* ``GET /``: health check, devuelve ``{"status": "ok"}``.
* ``POST /agente/preguntar``: envía una pregunta al agente y devuelve la
  respuesta junto con el historial actualizado de la conversación. Requiere un
  token de Supabase válido en el header ``Authorization``.

Manejo de errores
-----------------
* ``400``: la pregunta falta o está vacía (solo espacios).
* ``401``: falta el token, es inválido o está expirado.
* ``500``: el LLM o las tools fallaron. Al cliente se le devuelve un mensaje
  genérico; el detalle de la excepción se registra en el log del servidor.

El endpoint ``POST`` se declara con ``def`` (no ``async def``) a propósito:
:func:`preguntar` es bloqueante (llamadas HTTP al LLM y a Supabase), y FastAPI
ejecuta los endpoints síncronos en un *thread pool*, así no se bloquea el bucle
de eventos del servidor.
"""

import logging
import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import Client, create_client

from src.agente.llm_client import preguntar

logger = logging.getLogger(__name__)

#: Origen del frontend (Vite dev server).
ORIGEN_FRONTEND: str = "http://localhost:5173"


def _crear_cliente_supabase() -> Client:
    """Crea el cliente de Supabase con la anon key.

    Se usa la anon key (no la service_role) porque esta API solo necesita
    *validar tokens*. La escritura la hace el backend con la service_role.

    Raises:
        RuntimeError: si faltan las variables de entorno requeridas.
    """
    url = os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_ANON_KEY en las variables de entorno."
        )
    return create_client(url, anon_key)


_cliente_supabase: Client | None = None


def _obtener_cliente_supabase() -> Client:
    """Devuelve el cliente de Supabase, creándolo si hace falta."""
    global _cliente_supabase
    if _cliente_supabase is None:
        _cliente_supabase = _crear_cliente_supabase()
    return _cliente_supabase


def _validar_token(authorization: str | None) -> dict:
    """Valida el token de Supabase y devuelve el usuario.

    Raises:
        HTTPException(401): si el header falta, tiene un formato inválido o
            el token no es válido.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Falta el header Authorization.")
    partes = authorization.split(" ", 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Formato de Authorization inválido. Se espera 'Bearer <token>'.",
        )
    token = partes[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="El token está vacío.")
    try:
        respuesta = _obtener_cliente_supabase().auth.get_user(token)
    except Exception as e:
        logger.warning("Error al validar token con Supabase: %s", e)
        raise HTTPException(
            status_code=401, detail="Token inválido o expirado."
        ) from e
    if respuesta is None or respuesta.user is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    return {"id": respuesta.user.id, "email": respuesta.user.email}


def _dependencia_usuario(authorization: str | None = Header(default=None)) -> dict:
    """Dependencia de FastAPI: extrae y valida el token del header."""
    return _validar_token(authorization)


class PreguntaRequest(BaseModel):
    """Cuerpo de la petición a ``POST /agente/preguntar``.

    Attributes:
        pregunta: la pregunta del usuario en lenguaje natural.
        historial: historial previo de la conversación (sin el prompt del
            sistema), tal como lo devolvió una llamada anterior. ``None``
            empieza una conversación nueva.
    """

    pregunta: str
    historial: list[dict] | None = None


class PreguntaResponse(BaseModel):
    """Respuesta de ``POST /agente/preguntar``.

    Attributes:
        respuesta: texto de la respuesta del agente.
        historial: historial actualizado; se pasa tal cual en la próxima
            llamada para mantener el contexto de la conversación.
    """

    respuesta: str
    historial: list[dict]


app = FastAPI(title="API del Agente", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ORIGEN_FRONTEND],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check() -> dict[str, str]:
    """Health check: confirma que el servidor está arriba."""
    return {"status": "ok"}


@app.post("/agente/preguntar", response_model=PreguntaResponse)
def preguntar_endpoint(
    request: PreguntaRequest,
    usuario: dict = Depends(_dependencia_usuario),
) -> PreguntaResponse:
    """Envía una pregunta al agente y devuelve la respuesta.

    Requiere un token de Supabase válido en el header ``Authorization``.

    Raises:
        HTTPException(400): si la pregunta falta o está vacía.
        HTTPException(401): si el token falta o es inválido.
        HTTPException(500): si el LLM o las tools fallan.
    """
    if not request.pregunta or not request.pregunta.strip():
        raise HTTPException(
            status_code=400,
            detail="La pregunta no puede estar vacía.",
        )

    try:
        respuesta, historial_actualizado = preguntar(
            request.pregunta.strip(), request.historial
        )
    except Exception as e:
        logger.exception(
            "Error al consultar el agente para %s", usuario.get("email")
        )
        raise HTTPException(
            status_code=500,
            detail="Error interno al consultar el agente. Intenta de nuevo más tarde.",
        ) from e

    return PreguntaResponse(
        respuesta=respuesta,
        historial=historial_actualizado,
    )
