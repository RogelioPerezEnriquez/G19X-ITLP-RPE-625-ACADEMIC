"""Clasificación ABC de productos por importancia económica.

Módulo del motor OR: funciones puras y testeables. Recibe datos, devuelve
datos; no accede a red, base de datos ni sistema de archivos, y no imprime
ni registra nada.

El valor económico de un producto es ``costo_unitario`` x ``demanda_total``.
Los productos se ordenan de mayor a menor valor económico y ese valor se
acumula como porcentaje del total del catálogo:

* Clase A: porcentaje acumulado <= 80 %.
* Clase B: 80 % < porcentaje acumulado <= 95 %.
* Clase C: porcentaje acumulado > 95 %.
"""

import numpy as np
import pandas as pd

__all__ = ["clasificar_abc"]

# Columnas mínimas que debe traer el DataFrame de entrada.
COLUMNAS_REQUERIDAS: tuple[str, ...] = (
    "producto_id",
    "costo_unitario",
    "demanda_total",
)

# Umbrales de corte sobre el valor económico acumulado, en porcentaje.
# Fuente única de verdad: cuando el MVP incorpore la tabla de configuración,
# estos serán sus valores por defecto.
UMBRAL_CLASE_A: float = 80.0
UMBRAL_CLASE_B: float = 95.0

# Tolerancia al comparar porcentajes acumulados. Absorbe el ruido de punto
# flotante (p. ej. un acumulado real de 80 % representado como
# 80.00000000000001) sin alterar cortes con diferencias significativas.
TOLERANCIA_PCT: float = 1e-9


def clasificar_abc(productos: pd.DataFrame) -> pd.DataFrame:
    """
    Clasifica productos por importancia económica (A/B/C).

    Args:
        productos: DataFrame con al menos estas columnas:
            - producto_id: identificador único del producto
            - costo_unitario: costo por unidad (float >= 0)
            - demanda_total: suma histórica de demanda del producto (float >= 0)

    Returns:
        El mismo DataFrame con una nueva columna 'clase_abc' con valores
        'A', 'B' o 'C'. El orden original de las filas se preserva.

    Reglas:
        - El valor económico se calcula como costo_unitario * demanda_total.
        - Se ordenan de mayor a menor valor económico.
        - En caso de empate en el valor económico, se ordena secundariamente
          por producto_id ascendente para que el cálculo acumulado sea
          determinista. Este criterio es intencional y no debe eliminarse.
        - Clase A: acumulado <= 80%
        - Clase B: 80% < acumulado <= 95%
        - Clase C: acumulado > 95%

    Notas:
        - La función es pura: no modifica ``productos``, no hace I/O y no
          imprime ni registra nada.
        - El índice y el orden de las filas de ``productos`` se preservan tal
          cual (no se resetea el índice). Internamente se ordena por valor
          económico para calcular los acumulados y luego se deshace ese orden,
          asignando cada etiqueta a la fila del producto que corresponde.
        - Un producto que por sí solo represente más del 80 % del valor total
          será clase A. Es el comportamiento esperado, no un error.
        - Un catálogo con un solo producto (y valor económico total mayor que
          0) se clasifica como 'A': es un caso degenerado donde el 100 % de
          participación es un artefacto del tamaño del catálogo y no una señal
          de importancia relativa. Si ese único producto vale 0, se aplica la
          regla de valor total 0 (clase 'C').
        - Si el DataFrame está vacío, se devuelve una copia vacía con la
          columna 'clase_abc' (dtype object), sin lanzar excepción.
        - Si el valor económico total es 0 (todos los productos valen 0), todos
          los productos se asignan a clase 'C', sin dividir por cero.

    Raises:
        ValueError: si el DataFrame tiene filas pero le falta alguna de las
            columnas requeridas (producto_id, costo_unitario, demanda_total).
    """
    resultado: pd.DataFrame = productos.copy()

    # Un DataFrame vacío se devuelve vacío con la columna creada, incluso si no
    # trae todas las columnas requeridas (no hay nada que clasificar).
    if resultado.empty:
        resultado["clase_abc"] = pd.Series(index=resultado.index, dtype="object")
        return resultado

    _verificar_columnas(resultado)

    valor_economico: pd.Series = (
        resultado["costo_unitario"].astype("float64")
        * resultado["demanda_total"].astype("float64")
    )

    # Orden de cálculo: valor económico descendente y, ante empates,
    # producto_id ascendente (criterio determinista). Se guarda la posición
    # original de cada fila para poder deshacer el orden al final.
    por_valor: pd.DataFrame = pd.DataFrame(
        {
            "posicion": np.arange(resultado.shape[0], dtype=np.int64),
            "producto_id": resultado["producto_id"].to_numpy(),
            "valor_economico": valor_economico.to_numpy(dtype="float64"),
        }
    ).sort_values(
        by=["valor_economico", "producto_id"],
        ascending=[False, True],
        kind="mergesort",
    )

    total: float = float(por_valor["valor_economico"].sum())

    # Catálogo sin valor económico: no hay proporción que calcular.
    if not total > 0.0:
        resultado["clase_abc"] = np.full(resultado.shape[0], "C", dtype=object)
        return resultado

    # Caso degenerado: con un solo producto la participación es 100 % por
    # construcción, no por importancia relativa, así que se clasifica como 'A'.
    if resultado.shape[0] == 1:
        resultado["clase_abc"] = np.full(1, "A", dtype=object)
        return resultado

    porcentaje_acumulado: np.ndarray = (
        por_valor["valor_economico"].cumsum() / total * 100.0
    ).to_numpy(dtype="float64")

    # Los cortes son inclusivos y se evalúan con la tolerancia sumada al
    # umbral, de modo que un acumulado exactamente igual a 80 o a 95 quede
    # siempre del lado correcto aunque su representación flotante sea
    # levemente superior.
    por_valor["clase_abc"] = np.select(
        [
            porcentaje_acumulado <= UMBRAL_CLASE_A + TOLERANCIA_PCT,
            porcentaje_acumulado <= UMBRAL_CLASE_B + TOLERANCIA_PCT,
        ],
        ["A", "B"],
        default="C",
    ).astype(object)

    # Se restituye el orden original y se asigna de forma posicional, para no
    # depender de las etiquetas del índice (que pueden repetirse).
    en_orden_original: pd.DataFrame = por_valor.sort_values(
        by="posicion", kind="mergesort"
    )
    resultado["clase_abc"] = en_orden_original["clase_abc"].to_numpy(dtype=object)

    return resultado


def _verificar_columnas(productos: pd.DataFrame) -> None:
    """Valida que el DataFrame traiga las columnas requeridas.

    Args:
        productos: DataFrame de entrada de :func:`clasificar_abc`.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna for columna in COLUMNAS_REQUERIDAS if columna not in productos.columns
    ]
    if faltantes:
        raise ValueError(
            "clasificar_abc requiere las columnas "
            f"{', '.join(COLUMNAS_REQUERIDAS)}; faltan: {', '.join(faltantes)}."
        )

