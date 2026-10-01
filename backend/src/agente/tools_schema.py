"""Esquema JSON de las tools del agente para el protocolo de OpenAI (function calling).

El LLM (Z.ai / GLM, compatible con el protocolo de OpenAI) decide **qué**
función invocar a partir de la descripción y el esquema de argumentos que se le
pasan en el campo ``tools`` de ``chat.completions.create``. Este módulo es la
**fuente única** de ese esquema: expone :data:`TOOLS_SCHEMA`, una lista lista
para pasar tal cual al cliente LLM.

Correspondencia con :mod:`src.agente.tools`
-------------------------------------------
Hay **una entrada por cada una de las cinco tools** de ``tools.py`` y los
``name`` coinciden **exactamente** con los nombres de las funciones Python
(:func:`~src.agente.tools.buscar_recomendaciones`,
:func:`~src.agente.tools.detalle_recomendacion`,
:func:`~src.agente.tools.explicar_criterio`,
:func:`~src.agente.tools.comparar_proveedores`,
:func:`~src.agente.tools.resumen_prioridad_ABC_XYZ`). Los nombres de los
argumentos de ``properties`` coinciden con los parámetros de cada función
(``urgencia``, ``limite``, ``producto_nombre``, ``criterio``).

El ``supabase_client`` que reciben todas las tools en Python **no** aparece en
el esquema: es un detalle de implementación que el LLM nunca debe ver ni
elegir. :func:`src.agente.llm_client.preguntar` lo inyecta por su cuenta.

Valores de los enumerados
-------------------------
Los ``enum`` de ``urgencia`` y ``criterio`` se construyen a partir de
:data:`~src.agente.tools.URGENCIAS_VALIDAS` y
:data:`~src.agente.tools.CRITERIOS_VALIDOS`, respectivamente, para que el
esquema no se desincronice si cambian en ``tools.py``: una sola fuente de
verdad.

Contrato de las descripciones
-----------------------------
Las ``description`` están en español, sin jerga técnica innecesaria, y explican
**cuándo** usar cada tool, porque son el único criterio del LLM para elegirla.
"""

from src.agente.tools import CRITERIOS_VALIDOS, URGENCIAS_VALIDAS

__all__ = ["TOOLS_SCHEMA"]

#: Esquema de las cinco tools en el formato ``tools`` del protocolo de OpenAI.
#: Listo para pasarse a ``client.chat.completions.create(..., tools=TOOLS_SCHEMA)``.
TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "buscar_recomendaciones",
            "description": (
                "Lista las recomendaciones de compra ya generadas, ordenadas por "
                "prioridad (primero las más urgentes y con mayor ahorro estimado). "
                "Úsala para responder qué conviene comprar, qué es urgente o para "
                "listar recomendaciones. Permite filtrar por nivel de urgencia y "
                "limitar cuántas devuelve."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "urgencia": {
                        "type": "string",
                        "enum": list(URGENCIAS_VALIDAS),
                        "description": (
                            "Nivel de urgencia por el que filtrar. Si se omite, se "
                            "devuelven las recomendaciones de todos los niveles."
                        ),
                    },
                    "limite": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 20,
                        "description": (
                            "Número máximo de recomendaciones a devolver (entero "
                            "mayor o igual a 1). Por defecto, 20."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detalle_recomendacion",
            "description": (
                "Devuelve todos los datos de la recomendación de compra de un "
                "producto concreto: cantidad recomendada, stock, punto de reorden, "
                "ahorro estimado, proveedor elegido, clases ABC/XYZ, etc. El "
                "producto se identifica por su nombre exacto. Úsala cuando el "
                "usuario pida el detalle o los datos completos de un producto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_nombre": {
                        "type": "string",
                        "description": (
                            "Nombre exacto del producto tal como figura en el "
                            "sistema (no un identificador)."
                        ),
                    },
                },
                "required": ["producto_nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explicar_criterio",
            "description": (
                "Explica cómo quedó evaluado un criterio concreto de la "
                "recomendación de un producto: su estado y su valor numérico. Úsala "
                "cuando el usuario pregunte por qué se recomendó algo o cómo se "
                "evaluó un aspecto específico (riesgo de quiebre, ahorro, "
                "confiabilidad del proveedor, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_nombre": {
                        "type": "string",
                        "description": (
                            "Nombre exacto del producto tal como figura en el "
                            "sistema (no un identificador)."
                        ),
                    },
                    "criterio": {
                        "type": "string",
                        "enum": list(CRITERIOS_VALIDOS),
                        "description": (
                            "Criterio a explicar, identificado por su clave "
                            "interna. Las claves posibles son las del enumerado."
                        ),
                    },
                },
                "required": ["producto_nombre", "criterio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comparar_proveedores",
            "description": (
                "Compara los proveedores que pueden abastecer un producto y "
                "devuelve, para cada uno, su precio, tiempo de entrega, "
                "cumplimiento, tasa de defectos y un score calculado. El producto "
                "se identifica por su nombre exacto. Úsala cuando el usuario quiera "
                "saber qué proveedor conviene o comparar proveedores."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_nombre": {
                        "type": "string",
                        "description": (
                            "Nombre exacto del producto tal como figura en el "
                            "sistema (no un identificador)."
                        ),
                    },
                },
                "required": ["producto_nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumen_prioridad_ABC_XYZ",
            "description": (
                "Devuelve el panorama agregado del sistema: cuántas recomendaciones "
                "hay en total, cómo se reparten por clase ABC, por clase XYZ, por "
                "urgencia y por combinación ABC/XYZ, y el ahorro neto total "
                "estimado. Úsala para preguntas globales, como cuántas "
                "recomendaciones hay o cuál es la situación general."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
