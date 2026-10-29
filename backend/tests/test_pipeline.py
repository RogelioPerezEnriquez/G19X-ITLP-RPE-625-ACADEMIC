"""Tests del pipeline completo de recálculo (:mod:`src.pipeline`).

Se prueban dos garantías críticas del flujo:

* **El orden del recálculo**: las recomendaciones se generan en memoria
  ANTES de borrar las filas pendientes de la tabla ``recomendaciones``. Si
  el motor no genera nada, se aborta con ``ValueError`` sin tocar la base
  de datos (la tabla queda intacta).
* **El cruce de UUIDs**: :func:`src.pipeline._cruzar_uuid` exige un cruce
  1:1 entre las recomendaciones del motor y las filas que Supabase devuelve
  al insertar. Un ``producto_id`` repetido o una recomendación sin UUID
  abortan con ``ValueError`` en lugar de escribir evaluaciones cruzadas.

Para que los tests sean rápidos y herméticos (sin red ni Supabase ni motor
real) se usan :class:`unittest.mock.MagicMock` para el cliente de Supabase y
:func:`unittest.mock.patch` sobre las funciones que el pipeline importa
(``generar_recomendaciones``, ``guardar_recomendaciones`` y
``evaluar_y_guardar``).
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.pipeline import EVALUACIONES_POR_RECOMENDACION, _cruzar_uuid, ejecutar_pipeline_completo

# --------------------------------------------------------------- helpers


def _recomendaciones() -> pd.DataFrame:
    """DataFrame que simula la salida de ``generar_recomendaciones``."""
    return pd.DataFrame(
        {
            "producto_id": [1, 2],
            "cantidad_sugerida": [10, 20],
        }
    )


def _guardadas() -> pd.DataFrame:
    """DataFrame que simula las filas insertadas que Supabase devuelve."""
    return pd.DataFrame(
        {
            "id": ["uuid-1", "uuid-2"],
            "producto_id": [1, 2],
        }
    )


# ====================================================== orden del recálculo


def test_motor_vacio_no_borra_nada():
    """Si el motor no genera nada se aborta ANTES del DELETE.

    El ``ValueError`` debe lanzarse sin que el cliente de Supabase llegue a
    tocar ninguna tabla: ``cliente.table`` no se llama nunca, así que la
    tabla ``recomendaciones`` queda intacta.
    """
    cliente = MagicMock()
    with (
        patch(
            "src.pipeline.generar_recomendaciones",
            return_value=pd.DataFrame(),
        ),
        pytest.raises(ValueError, match="no generó recomendaciones"),
    ):
        ejecutar_pipeline_completo(cliente)

    cliente.table.assert_not_called()


def test_borra_solo_pendientes():
    """En el camino feliz el DELETE filtra por ``estado = 'pendiente'``.

    Solo se borran las pendientes; las marcadas como ``revisada`` o
    ``descartada`` ya fueron evaluadas por un usuario y se conservan.
    """
    cliente = MagicMock()
    with (
        patch(
            "src.pipeline.generar_recomendaciones",
            return_value=_recomendaciones(),
        ),
        patch(
            "src.pipeline.guardar_recomendaciones",
            return_value=_guardadas(),
        ),
        patch("src.pipeline.evaluar_y_guardar") as evaluar,
    ):
        resultado = ejecutar_pipeline_completo(cliente)

    cliente.table.assert_called_once_with("recomendaciones")
    cliente.table.return_value.delete.return_value.eq.assert_called_once_with(
        "estado", "pendiente"
    )
    evaluar.assert_called_once()
    assert resultado == {
        "recomendaciones_generadas": 2,
        "evaluaciones_generadas": 2 * EVALUACIONES_POR_RECOMENDACION,
    }


# ====================================================== cruce de UUIDs


def test_cruzar_uuid_producto_repetido():
    """Un ``producto_id`` repetido en las guardadas aborta el cruce.

    El conteo total por sí solo no lo detecta (dos filas de un producto y
    ninguna de otro suman lo mismo que un cruce correcto), así que se
    verifica explícitamente y se aborta con ``ValueError``.
    """
    guardadas = pd.DataFrame(
        {
            "id": ["uuid-1", "uuid-2"],
            "producto_id": [1, 1],
        }
    )

    with pytest.raises(ValueError, match="repetidos"):
        _cruzar_uuid(_recomendaciones(), guardadas)


def test_cruzar_uuid_cruce_incompleto():
    """Una recomendación sin UUID en las guardadas aborta el cruce.

    Si la respuesta del INSERT no trae una fila por recomendación generada,
    las evaluaciones quedarían incompletas o cruzadas, así que se aborta con
    ``ValueError``.
    """
    guardadas = pd.DataFrame(
        {
            "id": ["uuid-1"],
            "producto_id": [1],
        }
    )

    with pytest.raises(ValueError, match="cubre"):
        _cruzar_uuid(_recomendaciones(), guardadas)
