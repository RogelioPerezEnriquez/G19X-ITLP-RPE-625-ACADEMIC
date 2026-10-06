"""Levanta el servidor FastAPI del agente.

Uso:
    python scripts/run_api.py

Requiere:
- .env configurado en la raíz del proyecto.
- Dependencias instaladas: pip install -r backend/requirements.txt

Notas:
- Se inserta ``backend/`` en ``sys.path`` porque el proyecto usa imports
  absolutos desde ``src`` (p. ej. ``from src.agente.llm_client import
  preguntar``). La inserción está a nivel de módulo a propósito: con
  ``reload=True`` uvicorn crea un proceso hijo (*spawn*) que reimporta este
  script, así el hijo también hereda el ``sys.path`` correcto.
- La carga del ``.env`` aquí es una garantía extra: ``llm_client`` ya lo carga
  de forma perezosa desde la raíz, y ``load_dotenv`` no pisa variables ya
  definidas, así que ambas cargas son compatibles.
"""

import sys
from pathlib import Path

# Ajustar sys.path para importar desde backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.agente.api:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
