# scripts/verificar_agente_rapido.py

"""Verificación rápida del agente conversacional con Z.ai real.

Hace preguntas al agente y muestra las respuestas. Sirve para verificar:
- Que la conexión con Z.ai funciona.
- Que el agente responde con datos reales (grounding).
- Que el agente indica cuando no hay datos (RF-10).

Uso:
    python scripts/verificar_agente_rapido.py

Requiere:
- .env configurado (SUPABASE_URL, SUPABASE_ANON_KEY, LLM_API_KEY, etc.).
- Base de datos con o sin datos (el script funciona en ambos casos).
"""

import sys
from pathlib import Path

# Ajustar sys.path para importar desde backend/ (donde vive el paquete src)
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from src.agente.llm_client import preguntar


def preguntar_y_mostrar(pregunta: str, historial: list[dict] | None) -> list[dict]:
    """Hace una pregunta al agente y muestra la respuesta.

    Devuelve el historial actualizado para encadenar preguntas.
    """
    print(f"PREGUNTA: {pregunta}")
    print("-" * 60)
    respuesta, historial = preguntar(pregunta, historial)
    print(f"RESPUESTA: {respuesta}")
    print()
    return historial


def main() -> None:
    print("=" * 60)
    print("VERIFICACION DEL AGENTE CONVERSACIONAL")
    print("=" * 60)
    print()

    historial: list[dict] | None = None

    # Pregunta 1: consulta general
    historial = preguntar_y_mostrar("¿Hay recomendaciones criticas?", historial)

    # Pregunta 2: consulta de seguimiento (usa el historial)
    historial = preguntar_y_mostrar(
        "¿Y cual es el proveedor de ese producto?", historial
    )

    # Pregunta 3: producto inexistente (verifica RF-10)
    historial = preguntar_y_mostrar(
        "¿Que pasa con el producto INEXISTENTE_XYZ?", historial
    )

    # Preguntas adicionales para probar grounding con datos
    historial = preguntar_y_mostrar(
        "¿Que productos estan en atencion?", historial
    )
    historial = preguntar_y_mostrar(
        "Dame el detalle de SEED_Widget A", historial
    )
    historial = preguntar_y_mostrar(
        "¿Como se compara el proveedor de SEED_Engrane G7?", historial
    )
    historial = preguntar_y_mostrar(
        "Dame un resumen de prioridades ABC/XYZ", historial
    )

    print("=" * 60)
    print("FIN DE LA VERIFICACION")
    print("=" * 60)


if __name__ == "__main__":
    main()