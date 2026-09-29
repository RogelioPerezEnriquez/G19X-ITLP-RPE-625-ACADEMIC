"""Score de confiabilidad de proveedores y su clasificación por estado.

Módulo del motor OR: funciones puras y testeables. Recibe datos, devuelve
datos; no accede a red, base de datos ni sistema de archivos, y no imprime ni
registra nada.

El score combina dos señales del desempeño histórico del proveedor: el
cumplimiento de entrega (peso 0.6) y la calidad, entendida como la proporción
de unidades sin defectos (peso 0.4)::

    score = cumplimiento_entrega_pct * 0.6
          + (100 - tasa_defectos_pct) * 0.4

Con ambos insumos en [0, 100] el score también queda en [0, 100]: un proveedor
que entrega siempre a tiempo y sin defectos obtiene 100, y uno que nunca
entrega a tiempo y produce todo defectuoso obtiene 0.

Los cortes sobre el score definen el estado (MVP.md, sección 10, criterio 5):

* Confiable: score >= umbral_confiable (default 80).
* Aceptable con reservas: umbral_riesgoso <= score < umbral_confiable
  (default 60 <= score < 80).
* Riesgoso: score < umbral_riesgoso (default 60).

Los cortes se evalúan con una tolerancia de :data:`TOLERANCIA_SCORE` (1e-9) para
absorber el ruido de punto flotante: ``score >= umbral_confiable - 1e-9`` es
confiable y ``score < umbral_riesgoso - 1e-9`` es riesgoso. Sin esa tolerancia,
una combinación cuyo score matemático cae justo en un corte pero se representa
por debajo quedaría mal clasificada: cumplimiento 96 con defectos 94 da un score
matemático de 60 que en float64 vale 59.99999999999999, y sin tolerancia sería
"Riesgoso" en lugar de "Aceptable con reservas". La tolerancia es holgada frente
a ese ruido (del orden de 1e-14) y muchísimo menor que cualquier diferencia
relevante entre proveedores: para cambiar de estado hace falta una diferencia
de score muy superior a 1e-9, cuando las diferencias que importan en la
práctica son de décimas de punto. El mismo criterio usan :mod:`src.motor.abc`
(``TOLERANCIA_PCT``) y :mod:`src.motor.xyz` (``TOLERANCIA_CV``).

El módulo no agrupa: cada fila de entrada produce una fila de salida, así que un
``proveedor_id`` repetido aparecería repetido (el schema garantiza una fila por
proveedor, con ``id`` como clave primaria).

Los cortes sobre el score son parámetros de :func:`calcular_score_proveedor` y
sus valores por defecto vienen de :data:`src.config.PARAMETROS_DEFAULT`
(``score_proveedor_confiable`` = 80.0 y ``score_proveedor_riesgoso`` = 60.0),
que es la fuente única de verdad: cuando el MVP incorpore la tabla de
configuración, de ahí saldrán sus valores.

Los pesos de la fórmula (:data:`PESO_CUMPLIMIENTO`, :data:`PESO_CALIDAD`) y las
etiquetas de estado (:data:`ESTADO_CONFIABLE`, :data:`ESTADO_ACEPTABLE`,
:data:`ESTADO_RIESGOSO`) sí siguen siendo constantes de módulo, para que un
cambio de criterio se haga en un solo lugar.
"""

import numpy as np
import pandas as pd

from src.config import PARAMETROS_DEFAULT

__all__ = ["calcular_score_proveedor"]

# Columnas mínimas que debe traer el DataFrame de entrada.
COLUMNAS_REQUERIDAS: tuple[str, ...] = (
    "proveedor_id",
    "cumplimiento_entrega_pct",
    "tasa_defectos_pct",
)

# Los umbrales de corte sobre el score no viven aquí: son parámetros de
# :func:`calcular_score_proveedor` y su fuente única de verdad es
# src.config.PARAMETROS_DEFAULT ('score_proveedor_confiable' = 80.0 y
# 'score_proveedor_riesgoso' = 60.0), de donde se leen los defaults de la firma.

# Tolerancia al comparar el score con los umbrales. Absorbe el ruido de punto
# flotante (p. ej. un score matemático de 60 representado como
# 59.99999999999999) sin alterar cortes con diferencias significativas. Mismo
# criterio que TOLERANCIA_PCT en abc.py y TOLERANCIA_CV en xyz.py.
TOLERANCIA_SCORE: float = 1e-9

# Pesos de la fórmula. Suman 1.0, de modo que el score se expresa en la misma
# escala 0-100 que sus insumos.
PESO_CUMPLIMIENTO: float = 0.6
PESO_CALIDAD: float = 0.4

# Etiquetas de estado. Fuente única de verdad: los tests (y a futuro la API) las
# importan de aquí en lugar de repetir los literales.
ESTADO_CONFIABLE: str = "Confiable"
ESTADO_ACEPTABLE: str = "Aceptable con reservas"
ESTADO_RIESGOSO: str = "Riesgoso"


def calcular_score_proveedor(
    proveedores: pd.DataFrame,
    umbral_confiable: float = PARAMETROS_DEFAULT["score_proveedor_confiable"],
    umbral_riesgoso: float = PARAMETROS_DEFAULT["score_proveedor_riesgoso"],
) -> pd.DataFrame:
    """
    Calcula el score de confiabilidad y el estado de cada proveedor.

    Args:
        proveedores: DataFrame con una fila por proveedor. Columnas
            requeridas:
            - proveedor_id: identificador único del proveedor
            - cumplimiento_entrega_pct: % de entregas a tiempo (0-100)
            - tasa_defectos_pct: % de unidades defectuosas (0-100)
        umbral_confiable: score mínimo, en la escala 0-100 del score, para
            considerar a un proveedor "Confiable". Default 80.0, leído de
            ``config.PARAMETROS_DEFAULT['score_proveedor_confiable']``: un
            proveedor es "Confiable" si su score es >= umbral_confiable.
        umbral_riesgoso: score por debajo del cual un proveedor se considera
            "Riesgoso", en la escala 0-100 del score. Default 60.0, leído de
            ``config.PARAMETROS_DEFAULT['score_proveedor_riesgoso']``: un
            proveedor es "Riesgoso" si su score es < umbral_riesgoso, y queda
            en "Aceptable con reservas" todo el intervalo intermedio.

    Returns:
        DataFrame con una fila por proveedor, con columnas:
            - proveedor_id
            - score: valor de 0 a 100
            - estado: "Confiable", "Aceptable con reservas" o "Riesgoso"
        El orden de las filas es por proveedor_id ascendente.

    Reglas:
        - score = cumplimiento_entrega_pct * 0.6
                + (100 - tasa_defectos_pct) * 0.4
        - Estado (los cortes se comparan con TOLERANCIA_SCORE = 1e-9 de margen):
            "Confiable":              score >= umbral_confiable - 1e-9
            "Aceptable con reservas": umbral_riesgoso - 1e-9 <= score
                                      < umbral_confiable - 1e-9
            "Riesgoso":               score < umbral_riesgoso - 1e-9

    Notas:
        - La función es pura: no accede a red, DB ni archivos. No imprime
          ni registra nada.
        - No modifica el DataFrame de entrada.
        - La salida es un DataFrame nuevo, con RangeIndex desde 0.
        - Se asume que cumplimiento_entrega_pct y tasa_defectos_pct están en
          el rango [0, 100]; el schema de Supabase lo garantiza. No se
          valida ese rango aquí.
        - Orden de ejecución: primero se validan las columnas requeridas,
          luego el caso vacío, luego se calculan los scores.
        - 'proveedor_id' es de dtype object en la salida; 'score' es float64;
          'estado' es object.
        - Los dos umbrales son parámetros con default: quien no los pase
          obtiene exactamente el comportamiento histórico (80 y 60), porque sus
          defaults se leen de :data:`src.config.PARAMETROS_DEFAULT` y este
          módulo no guarda copias locales de esos valores.
        - Los umbrales se usan tal cual: no se validan sus rangos ni su orden
          (el módulo solo mantiene la validación estricta de columnas). Casos
          borde documentados: con umbral_confiable <= umbral_riesgoso la banda
          "Aceptable con reservas" queda vacía y cada proveedor es "Confiable"
          o "Riesgoso" según el primer corte; con umbral_confiable > 100 ningún
          proveedor del rango del schema (score <= 100) es "Confiable"; con
          umbral_riesgoso <= 0 ningún proveedor del rango (score >= 0) es
          "Riesgoso".
        - Los cortes se comparan con una tolerancia (TOLERANCIA_SCORE = 1e-9) en
          lugar de forma exacta: el score es un float y hay combinaciones cuyo
          valor matemático cae justo en un umbral pero se representan por
          debajo. Cumplimiento 96 con defectos 94 da un score matemático de 60
          que en float64 vale 59.99999999999999; con la tolerancia se clasifica
          como "Aceptable con reservas". Es el mismo criterio que TOLERANCIA_PCT
          en :mod:`src.motor.abc` y TOLERANCIA_CV en :mod:`src.motor.xyz`.

    Raises:
        ValueError: si al DataFrame le falta alguna columna requerida, tenga
            o no filas.
    """

    tabla: pd.DataFrame = proveedores.copy()

    # Validación estricta: se hace antes de cualquier atajo por DataFrame
    # vacío, de modo que un DataFrame sin filas y sin columnas también falla.
    _verificar_columnas(tabla)

    # Si no hay filas no hay nada que calcular: se devuelve la salida vacía con
    # las columnas y dtypes correctos.
    if tabla.empty:
        return _resultado_vacio()

    proveedor_id: np.ndarray = tabla["proveedor_id"].to_numpy(dtype=object)
    cumplimiento: np.ndarray = tabla["cumplimiento_entrega_pct"].to_numpy(
        dtype="float64"
    )
    defectos: np.ndarray = tabla["tasa_defectos_pct"].to_numpy(dtype="float64")

    # Calidad: porcentaje de unidades sin defectos. La tasa llega en %, de ahí el
    # 100. Se calcula vectorizado, igual que el resto de la fórmula.
    calidad: np.ndarray = 100.0 - defectos

    score: np.ndarray = cumplimiento * PESO_CUMPLIMIENTO + calidad * PESO_CALIDAD

    # Los cortes son exhaustivos y mutuamente excluyentes: >= umbral_confiable
    # es confiable, < umbral_riesgoso es riesgoso y todo lo demás (el intervalo
    # [umbral_riesgoso, umbral_confiable)) es aceptable con reservas. 'Aceptable
    # con reservas' va como default para no repetir la condición del intervalo.
    # A ambos umbrales se les resta TOLERANCIA_SCORE para absorber el ruido de
    # punto flotante (p. ej. un score matemático de 60 que en float64 vale
    # 59.99999999999999) sin mover ningún corte con diferencia significativa.
    estado: np.ndarray = np.select(
        [
            score >= umbral_confiable - TOLERANCIA_SCORE,
            score < umbral_riesgoso - TOLERANCIA_SCORE,
        ],
        [
            ESTADO_CONFIABLE,
            ESTADO_RIESGOSO,
        ],
        default=ESTADO_ACEPTABLE,
    )

    resultado: pd.DataFrame = pd.DataFrame(
        {
            "proveedor_id": pd.Series(proveedor_id, dtype=object),
            "score": pd.Series(score, dtype="float64"),
            "estado": pd.Series(estado, dtype=object),
        }
    )

    # Orden determinista: proveedor_id ascendente. Se ordena explícitamente para
    # que la garantía no dependa del orden de entrada. 'mergesort' es estable,
    # igual que en abc.py, xyz.py, demanda.py y eoq_rop.py.
    return resultado.sort_values(by="proveedor_id", kind="mergesort").reset_index(
        drop=True
    )


def _resultado_vacio() -> pd.DataFrame:
    """Devuelve el resultado vacío, con las columnas y dtypes de la salida.

    Returns:
        DataFrame sin filas con las columnas proveedor_id (object), score
        (float64) y estado (object), y con un RangeIndex vacío.
    """
    return pd.DataFrame(
        {
            "proveedor_id": pd.Series(dtype=object),
            "score": pd.Series(dtype="float64"),
            "estado": pd.Series(dtype=object),
        }
    )


def _verificar_columnas(proveedores: pd.DataFrame) -> None:
    """Valida que el DataFrame traiga las columnas requeridas.

    Args:
        proveedores: DataFrame de entrada de :func:`calcular_score_proveedor`.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna
        for columna in COLUMNAS_REQUERIDAS
        if columna not in proveedores.columns
    ]
    if faltantes:
        raise ValueError(
            "calcular_score_proveedor requiere las columnas "
            f"{', '.join(COLUMNAS_REQUERIDAS)}; faltan: {', '.join(faltantes)}."
        )
