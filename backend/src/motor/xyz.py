"""Clasificación XYZ de productos por variabilidad de su demanda histórica.

Módulo del motor OR: funciones puras y testeables. Recibe datos, devuelve
datos; no accede a red, base de datos ni sistema de archivos, y no imprime
ni registra nada.

La variabilidad de un producto se mide con el coeficiente de variación (CV)
de su demanda histórica, usando la desviación estándar **muestral**::

    CV = std_muestral(cantidad_demandada) / media(cantidad_demandada)

Los cortes sobre el CV son parámetros de :func:`clasificar_xyz` y sus valores
por defecto vienen de :data:`src.config.PARAMETROS_DEFAULT`
(``cv_confianza_alta`` y ``cv_confianza_media``), que son los que describen la
regla original:

* Clase X: CV <= umbral_x (default 0.5, demanda estable).
* Clase Y: umbral_x < CV <= umbral_y (default 0.5 < CV <= 1.0, demanda con
  variación moderada).
* Clase Z: CV > umbral_y (default CV > 1.0, demanda errática).

Ojo con los nombres: los parámetros se llaman ``umbral_x`` y ``umbral_y``
(coherente con las clases X/Y/Z de este módulo), pero sus defaults se leen de
las claves ``cv_confianza_alta`` y ``cv_confianza_media`` de la tabla de
configuración (db/schema.sql), que llevan el nombre del criterio que los usa:
la confianza en la demanda.

El CV que devuelve este módulo es la fuente única de verdad para la
clasificación XYZ y para el criterio de confianza en la demanda estimada
(MVP.md, sección 9, criterio 3): se calcula una sola vez por producto y se
reutiliza, en lugar de recalcularlo aguas abajo. Los cortes de ese criterio son
estos mismos ``umbral_x`` y ``umbral_y``.

A diferencia de :mod:`src.motor.abc`, aquí un producto puede no tener CV
calculable (media cero o menos de dos periodos de historia). Esos casos se
resuelven devolviendo ``None`` o excluyendo la fila, nunca lanzando una
excepción. La validación de las columnas requeridas, en cambio, es estricta:
se exige siempre, tenga o no filas el DataFrame de entrada.
"""

import numpy as np
import pandas as pd

from src.config import PARAMETROS_DEFAULT

__all__ = ["clasificar_xyz"]

# Columnas mínimas que debe traer el DataFrame de entrada.
COLUMNAS_REQUERIDAS: tuple[str, ...] = (
    "producto_id",
    "cantidad_demandada",
)

# Los umbrales de corte sobre el CV no viven aquí: son parámetros de
# :func:`clasificar_xyz` y su fuente única de verdad es
# src.config.PARAMETROS_DEFAULT ('cv_confianza_alta' = 0.5 y
# 'cv_confianza_media' = 1.0), de donde se leen los defaults de la firma. Los
# nombres de los parámetros siguen las clases X/Y/Z de este módulo; las claves
# de config siguen el nombre del criterio que las usa (db/schema.sql: la
# confianza en la demanda).

# Tolerancia al comparar el CV con los umbrales. Absorbe el ruido de punto
# flotante (p. ej. un CV real de 0.5 representado como 0.5000000000000001) sin
# alterar cortes con diferencias significativas.
TOLERANCIA_CV: float = 1e-9

# Mínimo de periodos con demanda observada para poder calcular la desviación
# estándar muestral. Con 0 o 1 observaciones el producto queda fuera.
MIN_PERIODOS: int = 2


def clasificar_xyz(
    historial: pd.DataFrame,
    umbral_x: float = PARAMETROS_DEFAULT["cv_confianza_alta"],
    umbral_y: float = PARAMETROS_DEFAULT["cv_confianza_media"],
) -> pd.DataFrame:
    """
    Clasifica productos por variabilidad de su demanda histórica (X/Y/Z).

    Args:
        historial: DataFrame con una fila por (producto, periodo). Columnas
            requeridas:
            - producto_id: identificador único del producto
            - cantidad_demandada: cantidad demandada en ese periodo (float >= 0)
        umbral_x: CV máximo de la clase X (demanda estable), en fracción (no en
            porcentaje). Default 0.5, leído de
            ``config.PARAMETROS_DEFAULT['cv_confianza_alta']``: un producto
            entra en la clase X si su CV es <= umbral_x. Es también el corte
            "CV alto" del criterio 3 (confianza en la demanda) de
            :mod:`src.evaluador`.
        umbral_y: CV máximo de la clase Y (demanda con variación moderada), en
            fracción (no en porcentaje). Default 1.0, leído de
            ``config.PARAMETROS_DEFAULT['cv_confianza_media']``: un producto
            entra en la clase Y si su CV es <= umbral_y y no entró en la clase
            X. Para que la banda Y no quede vacía debe cumplirse
            umbral_x <= umbral_y; el orden no se valida aquí (ver Notas). Es
            también el corte "CV moderado" del criterio 3 de
            :mod:`src.evaluador`.

    Returns:
        DataFrame con una fila por producto, con columnas:
            - producto_id
            - cv: coeficiente de variación (float o None si no calculable)
            - clase_xyz: 'X', 'Y', 'Z' o None si no calculable
        Solo se incluyen productos con al menos 2 periodos de historia.
        Los productos con 0 o 1 periodos se excluyen de la salida.
        Los productos con media cero (todos los periodos en 0) se incluyen
        con cv=None y clase_xyz=None.

    Reglas:
        - CV = std(cantidad_demandada, ddof=1) / mean(cantidad_demandada)
        - Clase X: CV <= umbral_x (default CV <= 0.5)
        - Clase Y: umbral_x < CV <= umbral_y (default 0.5 < CV <= 1.0)
        - Clase Z: CV > umbral_y (default CV > 1.0)
        - Producto con menos de 2 periodos: se excluye (no se puede calcular
          desviación estándar).
        - Producto con media cero (todos los periodos en 0): cv=None,
          clase_xyz=None. NO lanzar excepción.
        - Producto con desviación estándar cero y media > 0: CV = 0, clase X.
        - El orden de las filas de salida se ordena por producto_id
          ascendente para que sea determinista.

    Notas:
        - La función es pura: no accede a red, DB ni archivos. No imprime
          ni registra nada.
        - No modifica el DataFrame de entrada.
        - Se usa desviación estándar muestral (ddof=1), no poblacional.
        - El CV se calcula una sola vez por producto y se reutiliza para XYZ
          y para el criterio de confianza en la demanda (ver MVP.md sección 9).
        - Los dos umbrales son parámetros con default: quien no los pase obtiene
          exactamente el comportamiento histórico (0.5 y 1.0), porque sus
          defaults se leen de :data:`src.config.PARAMETROS_DEFAULT` y este
          módulo no guarda copias locales de esos valores.
        - Los umbrales se usan tal cual: no se validan sus rangos ni su orden
          (el módulo solo mantiene la validación estricta de columnas). Casos
          borde documentados: con ``umbral_x`` > 0 y ``umbral_y`` <=
          ``umbral_x`` la banda Y queda vacía y cada producto es X o Z según el
          primer corte; con ``umbral_x`` < 0 ningún producto es X salvo uno de
          desviación cero (CV = 0), que entra por :data:`TOLERANCIA_CV`.
        - El criterio 3 (confianza en la demanda) de :mod:`src.evaluador` usa
          estos mismos cortes, pero hoy los tiene duplicados en sus constantes
          ``CV_ALTA`` (0.5) y ``CV_MODERADA`` (1.0): pasar umbrales custom aquí
          NO mueve la rúbrica del evaluador mientras ese módulo no lea sus
          parámetros de configuración.
        - La salida es un DataFrame nuevo, con una fila por producto (no una
          copia de la entrada con una columna añadida), con un RangeIndex
          nuevo desde 0.
        - 'producto_id' y 'clase_xyz' son de dtype object; 'cv' también es
          object en la salida con filas, porque debe poder contener None
          (un CV calculable se guarda como float de Python).
        - Un periodo sin demanda observada (NaN/None en cantidad_demandada) no
          cuenta como periodo de historia: el mínimo de 2 periodos y los
          estadísticos se calculan sobre los valores no nulos del producto.
        - Una media <= 0 no tiene CV definido, así que devuelve cv=None (no
          solo el caso exacto de media cero).
        - Un producto sin CV calculable sigue apareciendo en la salida, con
          cv=None y clase_xyz=None, como marca explícita de "sin datos
          suficientes" en lugar de desaparecer en silencio.

    Raises:
        ValueError: si al DataFrame le falta alguna de las columnas requeridas
            (producto_id, cantidad_demandada), tenga o no tenga filas.
    """
    datos: pd.DataFrame = historial.copy()

    # Validación estricta: se hace antes de cualquier atajo por DataFrame
    # vacío, de modo que un DataFrame sin filas y sin columnas también falla.
    _verificar_columnas(datos)

    if datos.empty:
        return _resultado_vacio()

    agrupado: pd.DataFrame = (
        datos.assign(_demanda_xyz=datos["cantidad_demandada"].astype("float64"))
        # sort=True: las filas salen ya ordenadas por producto_id ascendente.
        # dropna=False: un producto_id nulo no debe hacer desaparecer filas.
        .groupby("producto_id", sort=True, dropna=False)["_demanda_xyz"]
        # 'count' (no 'size') cuenta solo observaciones no nulas, y el 'std' de
        # groupby es muestral por defecto (ddof=1), que es el que exige el CV.
        .agg(periodos="count", media="mean", desviacion="std")
        .reset_index()
    )

    # Con menos de 2 observaciones no existe desviación estándar muestral: el
    # producto no es clasificable y no forma parte de la salida.
    clasificables: pd.DataFrame = agrupado[agrupado["periodos"] >= MIN_PERIODOS]
    if clasificables.empty:
        return _resultado_vacio()

    media: np.ndarray = clasificables["media"].to_numpy(dtype="float64")
    desviacion: np.ndarray = clasificables["desviacion"].to_numpy(dtype="float64")

    # El CV está definido con media positiva; con media <= 0 (todos los
    # periodos en 0) el producto se conserva pero con cv y clase nulos.
    tiene_cv: np.ndarray = media > 0.0

    cv: np.ndarray = np.full(media.shape[0], np.nan, dtype="float64")
    np.divide(desviacion, media, out=cv, where=tiene_cv)

    # Los cortes son inclusivos y se evalúan con la tolerancia sumada al
    # umbral, de modo que un CV exactamente igual a umbral_x o a umbral_y quede
    # siempre del lado correcto aunque su representación flotante sea superior.
    clase: np.ndarray = np.select(
        [
            tiene_cv & (cv <= umbral_x + TOLERANCIA_CV),
            tiene_cv & (cv <= umbral_y + TOLERANCIA_CV),
        ],
        ["X", "Y"],
        default="Z",
    )

    resultado: pd.DataFrame = pd.DataFrame(
        {
            "producto_id": pd.Series(
                clasificables["producto_id"].to_numpy(dtype=object), dtype=object
            ),
            "cv": pd.Series(
                [
                    float(valor) if calculable else None
                    for valor, calculable in zip(cv.tolist(), tiene_cv.tolist())
                ],
                dtype=object,
            ),
            "clase_xyz": pd.Series(
                [
                    str(etiqueta) if calculable else None
                    for etiqueta, calculable in zip(clase.tolist(), tiene_cv.tolist())
                ],
                dtype=object,
            ),
        }
    )

    # Orden determinista: producto_id ascendente. Se ordena explícitamente
    # (aunque el groupby ya ordene) para que la garantía no dependa de detalles
    # internos de pandas. 'mergesort' es estable, igual que en abc.py.
    return resultado.sort_values(by="producto_id", kind="mergesort").reset_index(
        drop=True
    )


def _resultado_vacio() -> pd.DataFrame:
    """Devuelve el resultado vacío, con las columnas y dtypes de la salida.

    Returns:
        DataFrame sin filas con las columnas producto_id, cv y clase_xyz. Al no
        haber filas, 'cv' queda como float64 (no puede contener None);
        producto_id y clase_xyz son object.
    """
    return pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "cv": pd.Series(dtype="float64"),
            "clase_xyz": pd.Series(dtype=object),
        }
    )


def _verificar_columnas(historial: pd.DataFrame) -> None:
    """Valida que el DataFrame traiga las columnas requeridas.

    Args:
        historial: DataFrame de entrada de :func:`clasificar_xyz`.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna for columna in COLUMNAS_REQUERIDAS if columna not in historial.columns
    ]
    if faltantes:
        raise ValueError(
            "clasificar_xyz requiere las columnas "
            f"{', '.join(COLUMNAS_REQUERIDAS)}; faltan: {', '.join(faltantes)}."
        )
