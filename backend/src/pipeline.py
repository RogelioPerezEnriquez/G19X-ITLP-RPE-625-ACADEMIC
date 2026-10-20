"""Pipeline completo de recomendaciones y evaluaciones, sin interacción.

Este módulo empaqueta en una sola función el flujo que antes solo existía en el
script interactivo ``scripts/demo_flujo_completo.py``: limpiar la tabla
``recomendaciones``, regenerar las recomendaciones con el motor OR, guardarlas,
cruzar los UUID que Supabase asigna al insertar y aplicar la rúbrica de 6
criterios, guardando el resultado en ``evaluaciones_criterios``.

A diferencia del script, aquí no hay ``input()``, ``print()`` ni ``sys.exit()``:
la función hace el trabajo y devuelve los conteos, y cualquier error se propaga
tal cual para que el llamador (el endpoint de la API) decida cómo reportarlo.

La limpieza es un solo ``DELETE`` sobre ``recomendaciones``: la tabla
``evaluaciones_criterios`` declara su clave foránea hacia ``recomendaciones``
con ``on delete cascade`` (ver ``db/schema.sql``), así que las evaluaciones
asociadas se borran en cascada y no hay que eliminarlas a mano.

El cliente de Supabase que recibe :func:`ejecutar_pipeline_completo` debe estar
creado con la ``service_role key``: las tablas que escribe el flujo tienen RLS
habilitado con políticas de solo lectura, así que la ``anon key`` no alcanza.
"""

import pandas as pd

from src.evaluador import ORDEN_CRITERIOS, evaluar_y_guardar
from src.recomendador import generar_recomendaciones, guardar_recomendaciones

# Nombre de la tabla que limpia y escribe el flujo.
TABLA_RECOMENDACIONES: str = "recomendaciones"

# Evaluaciones que produce la rúbrica por recomendación: una fila por
# (recomendacion_id, criterio). Se deriva de ORDEN_CRITERIOS (fuente única de
# verdad del evaluador) en lugar de escribir un 6 a mano.
EVALUACIONES_POR_RECOMENDACION: int = len(ORDEN_CRITERIOS)

# UUID nulo usado como filtro del DELETE: PostgREST exige al menos un filtro en
# los DELETE, y ``id != <uuid nulo>`` es la forma de decir "todas las filas".
_UUID_NULO: str = "00000000-0000-0000-0000-000000000000"



def ejecutar_pipeline_completo(supabase_client) -> dict:
    """Ejecuta el pipeline completo: limpia, genera, guarda, cruza UUIDs
    y evalúa los 6 criterios.

    Args:
        supabase_client: cliente de Supabase con service_role key.

    Returns:
        dict con:
        - "recomendaciones_generadas": int (cantidad)
        - "evaluaciones_generadas": int (cantidad)

    Raises:
        Exception: cualquier error de Supabase, del motor o del evaluador
            se propaga tal cual.
        ValueError: si el cruce de UUIDs no cuadra (ver :func:`_cruzar_uuid`).
    """
    # Paso 1: limpiar la tabla. El `on delete cascade` de
    # `evaluaciones_criterios.recomendacion_id` borra las evaluaciones
    # asociadas, así que no hay que tocar esa tabla.
    supabase_client.table(TABLA_RECOMENDACIONES).delete().neq(
        "id", _UUID_NULO
    ).execute()

    # Paso 2: generar las recomendaciones con el motor OR.
    recomendaciones: pd.DataFrame = generar_recomendaciones(supabase_client)
    if recomendaciones.empty:
        return {"recomendaciones_generadas": 0, "evaluaciones_generadas": 0}

    # Paso 3: guardarlas (Supabase devuelve las filas insertadas con su UUID).
    guardadas: pd.DataFrame = guardar_recomendaciones(
        supabase_client, recomendaciones
    )

    # Paso 4: cruzar los UUID con las recomendaciones del motor.
    con_id: pd.DataFrame = _cruzar_uuid(recomendaciones, guardadas)

    # Paso 5: aplicar la rúbrica de 6 criterios y guardar las evaluaciones.
    evaluar_y_guardar(supabase_client, con_id)

    return {
        "recomendaciones_generadas": len(recomendaciones),
        "evaluaciones_generadas": len(con_id) * EVALUACIONES_POR_RECOMENDACION,
    }


def _cruzar_uuid(
    recomendaciones: pd.DataFrame,
    guardadas: pd.DataFrame,
) -> pd.DataFrame:
    """Cruza los UUID recién guardados con las recomendaciones del motor.

    Esta función es una copia de ``_recomendaciones_con_id`` de
    ``scripts/demo_flujo_completo.py``; se duplica aquí para no hacer que
    ``backend/src/`` dependa de ``scripts/``.

    Args:
        recomendaciones: DataFrame devuelto por
            :func:`src.recomendador.generar_recomendaciones` (una fila por
            producto, sin ``recomendacion_id``).
        guardadas: DataFrame devuelto por
            :func:`src.recomendador.guardar_recomendaciones` (las filas
            insertadas, con ``id`` y ``producto_id``).

    Returns:
        Copia de ``recomendaciones`` con la columna ``recomendacion_id`` (el
        UUID de la recomendación persistida), con una fila por recomendación.
        Es la entrada que espera :func:`src.evaluador.evaluar_y_guardar`.

    Raises:
        ValueError: si a ``guardadas`` le faltan las columnas ``id`` o
            ``producto_id``; si algún UUID viene nulo o vacío; si la respuesta
            del ``insert`` trae un ``producto_id`` repetido; o si el cruce no
            cubre exactamente las recomendaciones generadas. Los dos últimos
            casos significan que no se puede asociar cada evaluación a la
            recomendación correcta, así que se aborta en lugar de escribir
            filas cruzadas.
    """
    faltantes: list[str] = [
        columna
        for columna in ("id", "producto_id")
        if columna not in guardadas.columns
    ]
    if faltantes:
        raise ValueError(
            "las recomendaciones guardadas no traen las columnas necesarias "
            f"para cruzar los UUID; faltan: {', '.join(faltantes)}."
        )

    con_id: pd.DataFrame = guardadas[["id", "producto_id"]].rename(
        columns={"id": "recomendacion_id"}
    )
    ids: pd.Series = con_id["recomendacion_id"]
    if ids.isna().any() or (ids.astype(str).str.strip() == "").any():
        raise ValueError(
            "Supabase no devolvió un UUID válido para alguna recomendación; "
            "sin 'recomendacion_id' el INSERT de las evaluaciones fallaría "
            "por clave foránea."
        )

    # El cruce tiene que ser 1:1. Se verifica por los dos lados: un producto
    # repetido en la respuesta del insert (o una recomendación sin UUID) haría
    # que las evaluaciones se asociaran a la recomendación equivocada, y el
    # conteo total por sí solo no lo detecta (dos filas de un producto y
    # ninguna de otro suman lo mismo que un cruce correcto).
    if con_id["producto_id"].duplicated().any():
        repetidos = con_id.loc[
            con_id["producto_id"].duplicated(), "producto_id"
        ]
        raise ValueError(
            "la respuesta del INSERT trae productos repetidos "
            f"({len(repetidos)} repeticiones: "
            f"{', '.join(map(str, repetidos))}). El motor emite una "
            "recomendación por producto, así que hay filas duplicadas en la "
            "tabla: limpie 'recomendaciones' o filtre por "
            "'fecha_generacion'/'estado' antes de continuar, porque no se "
            "puede saber a qué recomendación corresponden las evaluaciones."
        )

    resultado: pd.DataFrame = recomendaciones.merge(
        con_id, on="producto_id", how="inner"
    )

    sin_uuid: list = sorted(
        set(recomendaciones["producto_id"]) - set(resultado["producto_id"]),
        key=str,
    )
    if sin_uuid or len(resultado) != len(recomendaciones):
        raise ValueError(
            f"el cruce por 'producto_id' cubre {len(resultado)} de "
            f"{len(recomendaciones)} recomendaciones (sin UUID: "
            f"{len(sin_uuid)}): la respuesta del INSERT no trae una fila por "
            "recomendación generada, así que las evaluaciones quedarían "
            "incompletas o cruzadas."
        )

    return resultado

