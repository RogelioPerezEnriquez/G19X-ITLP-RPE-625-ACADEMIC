"""Estimación de la demanda por periodo con promedio móvil.

Módulo del motor OR: funciones puras y testeables. Recibe datos, devuelve
datos; no accede a red, base de datos ni sistema de archivos, y no imprime ni
registra nada.

La demanda esperada de un producto es el promedio aritmético de las cantidades
demandadas en sus ``ventana`` periodos más recientes::

    demanda_estimada = media(cantidad_demandada de los últimos `ventana` periodos)

El resultado es un único número por producto y está en la misma unidad que la
entrada: si los periodos del historial son mensuales, la salida es "demanda por
mes". Este módulo NO anualiza ni convierte unidades; cuando la anualización sea
necesaria, es responsabilidad de :mod:`src.motor.eoq_rop`.

A diferencia de :mod:`src.motor.xyz`, aquí no existe el caso "sin datos
suficientes": el historial llega en formato largo (una fila por producto y
periodo), así que todo producto con al menos un periodo es estimable, incluso
si todos sus periodos valen 0 (una media de 0 es información válida, no un
error).

Los periodos se ordenan cronológicamente de forma ascendente antes de elegir la
ventana, y un producto con menos periodos que ``ventana`` se promedia con todo
lo que tenga (no se excluye). El resultado no depende del orden de las filas de
entrada.

El tamaño de la ventana es un parámetro de :func:`estimar_demanda` y su valor
por defecto viene de :data:`src.config.PARAMETROS_DEFAULT`
(``demanda_ventana_default``, 6.0), que es la fuente única de verdad: refleja la
fila correspondiente de la tabla ``parametros_configuracion`` y ya llega desde
ahí en el pipeline (``src.recomendador`` la lee con
:func:`src.config.cargar_parametros`).
"""

import pandas as pd

from src.config import PARAMETROS_DEFAULT

__all__ = ["estimar_demanda"]

# Columnas mínimas que debe traer el DataFrame de entrada.
COLUMNAS_REQUERIDAS: tuple[str, ...] = (
    "producto_id",
    "periodo",
    "cantidad_demandada",
)

# El tamaño de la ventana (número de periodos más recientes que se promedian)
# no vive aquí: es un parámetro de :func:`estimar_demanda` y su fuente única de
# verdad es src.config.PARAMETROS_DEFAULT ('demanda_ventana_default' = 6.0), de
# donde se lee el default de la firma. El cast a int() es explícito porque
# config devuelve todos los parámetros como float y 'ventana' debe ser int.


def estimar_demanda(
    historial: pd.DataFrame,
    ventana: int = int(PARAMETROS_DEFAULT["demanda_ventana_default"]),
) -> pd.DataFrame:
    """
    Estima la demanda por periodo para cada producto usando promedio móvil.

    Args:
        historial: DataFrame con una fila por (producto, periodo). Columnas
            requeridas:
            - producto_id: identificador único del producto
            - periodo: fecha del periodo (parseable como datetime)
            - cantidad_demandada: cantidad demandada (float >= 0)
        ventana: número de periodos más recientes a promediar, como int. Default
            6 (``config.PARAMETROS_DEFAULT['demanda_ventana_default']``, 6.0,
            convertido a int en la propia firma). Debe ser un entero positivo.
            Si un producto tiene menos periodos que `ventana`, se promedian
            todos los disponibles.

    Returns:
        DataFrame con una fila por producto, con columnas:
            - producto_id
            - demanda_estimada: promedio de los últimos `ventana` periodos
              (o de todos los disponibles). En la misma unidad que
              `cantidad_demandada` (por periodo).
        Solo se incluyen productos con al menos 1 periodo de historia.
        El orden de las filas es por producto_id ascendente.

    Reglas:
        - Los periodos se ordenan cronológicamente de forma ascendente antes
          de tomar la ventana. El resultado no depende del orden de las filas
          de entrada.
        - Productos sin historial: se excluyen de la salida.
        - Productos con menos periodos que `ventana`: se promedian los
          disponibles (no se excluyen).
        - Productos con todos los periodos en 0: demanda_estimada = 0
          (es información válida, no un error).

    Notas:
        - La función es pura: no accede a red, DB ni archivos. No imprime
          ni registra nada.
        - No modifica el DataFrame de entrada.
        - Se asume que no hay (producto_id, periodo) duplicados; el schema de
          Supabase lo garantiza con UNIQUE (producto_id, periodo).
        - La salida es un DataFrame nuevo, con RangeIndex desde 0.
        - Si el DataFrame está vacío pero trae las columnas requeridas, se
          devuelve un DataFrame vacío con las columnas producto_id (object) y
          demanda_estimada (float64), sin lanzar excepción.
        - La validación de `ventana` se hace antes que la del DataFrame, y la de
          las columnas antes que el atajo por DataFrame vacío, de modo que las
          reglas "ventana inválida" y "columnas faltantes" se cumplen siempre,
          tenga o no filas la entrada.
        - El default de `ventana` se lee de
          :data:`src.config.PARAMETROS_DEFAULT` con ``int()`` en la propia
          firma: config devuelve los parámetros como float (6.0) y la validación
          de `ventana` exige un int. Es un cambio de fuente, no de valor: el
          default sigue siendo 6.

    Raises:
        ValueError: si al DataFrame le falta alguna columna requerida
            (producto_id, periodo, cantidad_demandada), tenga o no filas.
        ValueError: si `ventana` no es un entero positivo.
        ValueError: si hay valores en `periodo` que no se pueden parsear como
            fecha. Cualquier excepción nativa de pandas al parsear (ParserError,
            TypeError, etc.) se captura y se relanza como ValueError con un
            mensaje claro, para que el contrato de la función sea estable
            independientemente de la versión de pandas.
    """
    # El parámetro escalar se valida primero: es la única validación que no
    # depende de los datos y por lo tanto aplica incluso si el historial está
    # vacío.
    _verificar_ventana(ventana)

    datos: pd.DataFrame = historial.copy()

    # Validación estricta: se hace antes de cualquier atajo por DataFrame
    # vacío, de modo que un DataFrame sin filas y sin columnas también falla.
    _verificar_columnas(datos)

    if datos.empty:
        return _resultado_vacio()

    # El parseo se hace una sola vez, sobre la copia local, y con un mensaje
    # propio. DateParseError de pandas y ParserError de dateutil derivan de
    # ValueError, así que capturar ValueError y TypeError cubre todas las
    # versiones: el contrato hacia afuera siempre es un ValueError del módulo.
    try:
        datos["periodo"] = pd.to_datetime(datos["periodo"], errors="raise")
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "estimar_demanda: la columna 'periodo' contiene valores que no se "
            "pueden interpretar como fecha."
        ) from exc

    # Orden cronológico ascendente dentro de cada producto. 'mergesort' es
    # estable, igual que en abc.py y xyz.py, para que el resultado no dependa
    # del orden de aparición de las filas.
    ordenado: pd.DataFrame = datos.sort_values(
        by=["producto_id", "periodo"], kind="mergesort"
    )

    # groupby(...).tail(N) devuelve los N últimos registros de cada grupo en el
    # orden en que aparecen, es decir, los N periodos más recientes. Un producto
    # con menos de N periodos conserva todos los que tiene.
    ultimos: pd.DataFrame = ordenado.groupby(
        "producto_id", sort=True, dropna=False
    ).tail(ventana)

    resultado: pd.DataFrame = (
        ultimos.assign(_demanda=ultimos["cantidad_demandada"].astype("float64"))
        # sort=True: las filas salen ya ordenadas por producto_id ascendente.
        # dropna=False: un producto_id nulo no debe hacer desaparecer filas.
        .groupby("producto_id", sort=True, dropna=False)["_demanda"]
        .mean()
        .rename("demanda_estimada")
        .reset_index()
    )

    # Orden determinista: producto_id ascendente. Se ordena explícitamente
    # (aunque el groupby ya ordene) para que la garantía no dependa de detalles
    # internos de pandas.
    return resultado.sort_values(by="producto_id", kind="mergesort").reset_index(
        drop=True
    )


def _resultado_vacio() -> pd.DataFrame:
    """Devuelve el resultado vacío, con las columnas y dtypes de la salida.

    Returns:
        DataFrame sin filas con las columnas producto_id (object) y
        demanda_estimada (float64), y con un RangeIndex vacío.
    """
    return pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "demanda_estimada": pd.Series(dtype="float64"),
        }
    )


def _verificar_ventana(ventana: int) -> None:
    """Valida que la ventana sea un entero positivo.

    Args:
        ventana: número de periodos a promediar, tal como llegó del llamador.

    Raises:
        ValueError: si `ventana` no es un entero o es menor que 1. Los booleanos
            se rechazan explícitamente: ``isinstance(True, int)`` es True en
            Python, pero True no es un tamaño de ventana válido.
    """
    if isinstance(ventana, bool) or not isinstance(ventana, int):
        raise ValueError(
            "estimar_demanda: 'ventana' debe ser un entero positivo; se recibió "
            f"{ventana!r} ({type(ventana).__name__})."
        )
    if ventana < 1:
        raise ValueError(
            "estimar_demanda: 'ventana' debe ser un entero positivo; se recibió "
            f"{ventana}."
        )


def _verificar_columnas(historial: pd.DataFrame) -> None:
    """Valida que el DataFrame traiga las columnas requeridas.

    Args:
        historial: DataFrame de entrada de :func:`estimar_demanda`.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna for columna in COLUMNAS_REQUERIDAS if columna not in historial.columns
    ]
    if faltantes:
        raise ValueError(
            "estimar_demanda requiere las columnas "
            f"{', '.join(COLUMNAS_REQUERIDAS)}; faltan: {', '.join(faltantes)}."
        )

