"""Cantidad económica de pedido (EOQ), stock de seguridad y punto de reorden.

Módulo del motor OR: funciones puras y testeables. Recibe datos, devuelve
datos; no accede a red, base de datos ni sistema de archivos, y no imprime ni
registra nada.

Para cada producto se calculan tres valores clásicos de gestión de inventario:

* Cantidad económica de pedido (EOQ)::

      EOQ = sqrt(2 * D * S / H)

  con ``D = demanda_estimada * periodos_por_año`` (demanda anual),
  ``S = costo_ordenar`` (costo por pedido) y
  ``H = costo_unitario * costo_mantener_pct_anual / 100`` (costo de mantener una
  unidad durante un año). ``H`` debe ser mayor que 0: si no, el EOQ no está
  definido y la función lanza ``ValueError``.

* Stock de seguridad (SS), el colchón que absorbe la variabilidad durante la
  espera de entrega::

      SS = demanda_diaria * lead_time_dias * margen_seguridad_pct

  con ``demanda_diaria = demanda_estimada / dias_por_periodo``.

* Punto de reorden (ROP), el nivel de inventario que dispara un nuevo pedido::

      ROP = demanda_diaria * lead_time_dias + SS

Unidades: ``demanda_estimada`` está en unidades por periodo, ``lead_time_dias``
en días, ``dias_por_periodo`` en días por periodo y ``periodos_por_año`` en
periodos por año. Con los defaults (12 y 30) el módulo asume periodos mensuales
y un año de 360 días; un llamador que trabaje con periodos semanales debe pasar
``periodos_por_año=52`` y ``dias_por_periodo=7`` para que las unidades sigan
siendo consistentes entre sí.

El módulo no agrupa: cada fila de entrada produce una fila de salida, así que un
``producto_id`` repetido aparecería repetido (el schema garantiza una fila por
producto). Tampoco anualiza ni convierte unidades por su cuenta: para la demanda
anualizada usa el factor ``periodos_por_año`` que recibe del llamador.

Los parámetros configurables viven en constantes de módulo
(:data:`PERIODOS_POR_AÑO_DEFAULT`, :data:`DIAS_POR_PERIODO_DEFAULT`,
:data:`MARGEN_SEGURIDAD_PCT_DEFAULT`) como fuente única de verdad: cuando el MVP
incorpore la tabla de configuración, esos serán sus valores por defecto.
"""

import numpy as np
import pandas as pd

__all__ = ["calcular_eoq_rop"]

# Columnas mínimas que debe traer el DataFrame de entrada.
COLUMNAS_REQUERIDAS: tuple[str, ...] = (
    "producto_id",
    "costo_unitario",
    "costo_ordenar",
    "costo_mantener_pct_anual",
    "demanda_estimada",
    "lead_time_dias",
)

# Periodos que tiene un año. Fuente única de verdad: cuando el MVP incorpore la
# tabla de configuración, este será su valor por defecto.
PERIODOS_POR_AÑO_DEFAULT: int = 12

# Días que tiene un periodo. Fuente única de verdad: cuando el MVP incorpore la
# tabla de configuración, este será su valor por defecto.
DIAS_POR_PERIODO_DEFAULT: int = 30

# Margen sobre el consumo esperado durante el lead time que se reserva como
# stock de seguridad. Fuente única de verdad: cuando el MVP incorpore la tabla
# de configuración, este será su valor por defecto.
MARGEN_SEGURIDAD_PCT_DEFAULT: float = 0.20


def calcular_eoq_rop(
    datos: pd.DataFrame,
    periodos_por_año: int = PERIODOS_POR_AÑO_DEFAULT,
    dias_por_periodo: int = DIAS_POR_PERIODO_DEFAULT,
    margen_seguridad_pct: float = MARGEN_SEGURIDAD_PCT_DEFAULT,
) -> pd.DataFrame:
    """
    Calcula EOQ, stock de seguridad y punto de reorden por producto.

    Args:
        datos: DataFrame con una fila por producto. Columnas requeridas:
            - producto_id
            - costo_unitario: costo por unidad (float >= 0)
            - costo_ordenar: costo por pedido (float >= 0)
            - costo_mantener_pct_anual: % anual de mantener (float >= 0)
            - demanda_estimada: demanda por periodo (float >= 0)
            - lead_time_dias: lead time del proveedor (int >= 0)
        periodos_por_año: número de periodos en un año. Default 12.
            Debe ser un entero positivo.
        dias_por_periodo: días que tiene un periodo. Default 30.
            Debe ser un entero positivo.
        margen_seguridad_pct: factor de margen para el stock de seguridad.
            Default 0.20 (20%). Debe ser un float >= 0.

    Returns:
        DataFrame con una fila por producto, con columnas:
            - producto_id
            - cantidad_eoq: cantidad económica de pedido
            - stock_seguridad: unidades de colchón
            - punto_reorden: nivel de inventario que dispara el pedido
        El orden de las filas es por producto_id ascendente.

    Reglas:
        - EOQ = sqrt(2 * D * S / H), donde:
            D = demanda_estimada * periodos_por_año
            S = costo_ordenar
            H = costo_unitario * (costo_mantener_pct_anual / 100)
        - Si H == 0 para algún producto, se lanza ValueError.
        - SS = (demanda_estimada / dias_por_periodo) * lead_time_dias
               * margen_seguridad_pct
        - ROP = (demanda_estimada / dias_por_periodo) * lead_time_dias + SS

    Notas:
        - La función es pura: no accede a red, DB ni archivos. No imprime
          ni registra nada.
        - No modifica el DataFrame de entrada.
        - La salida es un DataFrame nuevo, con RangeIndex desde 0.
        - Las unidades de entrada y salida son consistentes con la entrada
          (el llamador se encarga de unificar unidades si es necesario).
        - Orden de ejecución: primero se validan los parámetros escalares,
          luego las columnas requeridas, luego el caso vacío, y solo si hay
          filas se valida H == 0 y se calculan los valores.

    Raises:
        ValueError: si al DataFrame le falta alguna columna requerida, tenga
            o no filas.
        ValueError: si `periodos_por_año`, `dias_por_periodo` o
            `margen_seguridad_pct` no son válidos.
        ValueError: si el costo de mantener H (costo_unitario *
    costo_mantener_pct_anual / 100) no es mayor que 0 en algún producto.
    Sucede cuando costo_unitario == 0 o costo_mantener_pct_anual == 0.
    Solo aplica si el DataFrame tiene filas.
    """

    # Los parámetros escalares se validan primero: es la única validación que no
    # depende de los datos y por lo tanto aplica incluso si la entrada está
    # vacía.
    _verificar_entero_positivo("periodos_por_año", periodos_por_año)
    _verificar_entero_positivo("dias_por_periodo", dias_por_periodo)
    _verificar_margen_seguridad(margen_seguridad_pct)

    tabla: pd.DataFrame = datos.copy()

    # Validación estricta: se hace antes de cualquier atajo por DataFrame
    # vacío, de modo que un DataFrame sin filas y sin columnas también falla.
    _verificar_columnas(tabla)

    # Si no hay filas no hay nada que calcular: se devuelve la salida vacía con
    # las columnas y dtypes correctos, sin evaluar H.
    if tabla.empty:
        return _resultado_vacio()

    producto_id: np.ndarray = tabla["producto_id"].to_numpy(dtype=object)
    costo_unitario: np.ndarray = tabla["costo_unitario"].to_numpy(dtype="float64")
    costo_ordenar: np.ndarray = tabla["costo_ordenar"].to_numpy(dtype="float64")
    costo_mantener_pct: np.ndarray = tabla["costo_mantener_pct_anual"].to_numpy(
        dtype="float64"
    )
    demanda_estimada: np.ndarray = tabla["demanda_estimada"].to_numpy(dtype="float64")
    lead_time_dias: np.ndarray = tabla["lead_time_dias"].to_numpy(dtype="float64")

    # H: costo de mantener una unidad durante un año, en unidades monetarias por
    # unidad y por año. El porcentaje llega expresado en %, de ahí la división
    # entre 100.
    costo_mantener: np.ndarray = costo_unitario * (costo_mantener_pct / 100.0)

    # H > 0 es precondición del EOQ: si H no es positivo la raíz no está
    # definida (y con H == 0 habría además división por cero). El schema
    # garantiza costo_unitario >= 0 y costo_mantener_pct_anual >= 0, así que en
    # la práctica esto solo puede darse con H == 0 (costo_unitario == 0 o
    # costo_mantener_pct_anual == 0); en ese caso el producto no es planificable
    # con EOQ y se falla en lugar de devolver inf o nan.
    costo_mantener_invalido: np.ndarray = costo_mantener <= 0.0
    if bool(costo_mantener_invalido.any()):
        afectados: list[str] = _productos_afectados(
            producto_id, costo_mantener_invalido
        )
        raise ValueError(
            "calcular_eoq_rop: no se puede calcular el EOQ de los productos "
            f"{', '.join(afectados)}: el costo de mantener por unidad y año "
            "(H = costo_unitario * costo_mantener_pct_anual / 100) no es mayor "
            "que 0."
        )

    # Cálculos vectorizados, una fila por producto. H > 0 está garantizado, así
    # que no hay división por cero ni raíz de un valor negativo.
    demanda_anual: np.ndarray = demanda_estimada * periodos_por_año
    cantidad_eoq: np.ndarray = np.sqrt(
        2.0 * demanda_anual * costo_ordenar / costo_mantener
    )

    demanda_diaria: np.ndarray = demanda_estimada / dias_por_periodo
    # Consumo esperado durante el lead time del proveedor.
    consumo_lead_time: np.ndarray = demanda_diaria * lead_time_dias
    stock_seguridad: np.ndarray = consumo_lead_time * margen_seguridad_pct
    punto_reorden: np.ndarray = consumo_lead_time + stock_seguridad

    resultado: pd.DataFrame = pd.DataFrame(
        {
            "producto_id": pd.Series(producto_id, dtype=object),
            "cantidad_eoq": pd.Series(cantidad_eoq, dtype="float64"),
            "stock_seguridad": pd.Series(stock_seguridad, dtype="float64"),
            "punto_reorden": pd.Series(punto_reorden, dtype="float64"),
        }
    )

    # Orden determinista: producto_id ascendente. Se ordena explícitamente para
    # que la garantía no dependa del orden de entrada. 'mergesort' es estable,
    # igual que en abc.py, xyz.py y demanda.py.
    return resultado.sort_values(by="producto_id", kind="mergesort").reset_index(
        drop=True
    )


def _resultado_vacio() -> pd.DataFrame:
    """Devuelve el resultado vacío, con las columnas y dtypes de la salida.

    Returns:
        DataFrame sin filas con las columnas producto_id (object), cantidad_eoq,
        stock_seguridad y punto_reorden (float64), y con un RangeIndex vacío.
    """
    return pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "cantidad_eoq": pd.Series(dtype="float64"),
            "stock_seguridad": pd.Series(dtype="float64"),
            "punto_reorden": pd.Series(dtype="float64"),
        }
    )


def _verificar_entero_positivo(nombre: str, valor: object) -> None:
    """Valida que un parámetro escalar sea un entero positivo.

    Args:
        nombre: nombre del parámetro tal como aparece en la firma, para que el
            mensaje de error señale al llamador cuál corregir.
        valor: valor recibido, tal cual llegó del llamador.

    Raises:
        ValueError: si `valor` no es un entero o es menor que 1. Los booleanos
            se rechazan explícitamente: ``isinstance(True, int)`` es True en
            Python, pero True no es un tamaño válido.
    """
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError(
            f"calcular_eoq_rop: '{nombre}' debe ser un entero positivo; se "
            f"recibió {valor!r} ({type(valor).__name__})."
        )
    if valor < 1:
        raise ValueError(
            f"calcular_eoq_rop: '{nombre}' debe ser un entero positivo; se "
            f"recibió {valor}."
        )


def _verificar_margen_seguridad(margen: object) -> None:
    """Valida que el margen de seguridad sea un número no negativo.

    Args:
        margen: valor de `margen_seguridad_pct` tal como llegó del llamador.

    Raises:
        ValueError: si `margen` no es un número (int o float) o es negativo. Un
            int se acepta porque se interpreta igual que el float (0 == 0.0);
            los booleanos se rechazan explícitamente porque
            ``isinstance(True, int)`` es True pero True no es un margen.
    """
    if isinstance(margen, bool) or not isinstance(margen, (int, float)):
        raise ValueError(
            "calcular_eoq_rop: 'margen_seguridad_pct' debe ser un número >= 0; "
            f"se recibió {margen!r} ({type(margen).__name__})."
        )
    if margen < 0:
        raise ValueError(
            "calcular_eoq_rop: 'margen_seguridad_pct' debe ser un número >= 0; "
            f"se recibió {margen}."
        )


def _verificar_columnas(datos: pd.DataFrame) -> None:
    """Valida que el DataFrame traiga las columnas requeridas.

    Args:
        datos: DataFrame de entrada de :func:`calcular_eoq_rop`.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna for columna in COLUMNAS_REQUERIDAS if columna not in datos.columns
    ]
    if faltantes:
        raise ValueError(
            "calcular_eoq_rop requiere las columnas "
            f"{', '.join(COLUMNAS_REQUERIDAS)}; faltan: {', '.join(faltantes)}."
        )


def _productos_afectados(producto_id: np.ndarray, mascara: np.ndarray) -> list[str]:
    """IDs de los productos marcados por `mascara`, sin repetir y ordenados.

    Args:
        producto_id: array de identificadores, en el orden de las filas.
        mascara: array booleano, alineado posicionalmente con `producto_id`.

    Returns:
        Lista de IDs (como texto, para que el mensaje funcione con cualquier
        dtype) sin duplicados y en orden ascendente, de modo que el mensaje de
        error sea determinista.
    """
    afectados: list[object] = producto_id[mascara].tolist()
    return sorted({str(valor) for valor in afectados})

