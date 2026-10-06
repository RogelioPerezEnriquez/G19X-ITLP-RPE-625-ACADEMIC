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
  respuesta junto con el historial actualizado de la conversación.

Manejo de errores
-----------------
* ``400``: la pregunta falta o está vacía (solo espacios).
* ``500``: el LLM o las tools fallaron (se incluye el mensaje de la excepción).

El endpoint ``POST`` se declara con ``def`` (no ``async def``) a propósito:
:func:`preguntar` es bloqueante (llamadas HTTP al LLM y a Supabase), y FastAPI
ejecuta los endpoints síncronos en un *thread pool*, así no se bloquea el bucle
de eventos del servidor.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agente.llm_client import preguntar

#: Origen del frontend (Vite dev server).
ORIGEN_FRONTEND: str = "http://localhost:5173"


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
def preguntar_endpoint(request: PreguntaRequest) -> PreguntaResponse:
    """Envía una pregunta al agente y devuelve la respuesta.

    Args:
        request: la pregunta y, opcionalmente, el historial previo.

    Returns:
        La respuesta del agente y el historial actualizado.

    Raises:
        HTTPException(400): si la pregunta falta o está vacía.
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
        raise HTTPException(
            status_code=500,
            detail=f"Error al consultar el agente: {e}",
        ) from e

    return PreguntaResponse(
        respuesta=respuesta,
        historial=historial_actualizado,
    )
