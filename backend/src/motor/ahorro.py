"""Oportunidad de ahorro por descuento de volumen (criterio 6 de la rúbrica).

Módulo del motor OR: funciones puras y testeables. Recibe datos, devuelve
datos; no accede a red, base de datos ni sistema de archivos, y no imprime ni
registra nada.

Contexto: un proveedor puede ofrecer un descuento si el pedido alcanza cierta
cantidad mínima (``cantidad_umbral_descuento``). Si el EOQ natural (el que
calcula :mod:`src.motor.eoq_rop`) ya alcanza ese umbral, el descuento se cobra
sin tocar la cantidad; si no lo alcanza, **se sube el pedido hasta el umbral**
para acceder al descuento, a cambio de mantener inventario por encima del
óptimo. El criterio se llama "oportunidad de ahorro por volumen" justamente
porque lo que se evalúa es si conviene subir el pedido, así que el "solo si
cantidad_EOQ >= cantidad_umbral_descuento" de la fórmula abreviada de ``MVP.md``
§10 se lee como el caso que ya accede al descuento sin tocar la cantidad, no
como una prohibición de subirla. El módulo cuantifica ese intercambio:

* Cantidad pedida::

      cantidad_pedido = cantidad_eoq
                        si el producto no tiene descuento
                        o si cantidad_eoq >= cantidad_umbral_descuento
      cantidad_pedido = cantidad_umbral_descuento
                        si cantidad_eoq < cantidad_umbral_descuento

* Cantidad extra, solo cuando hubo que subir el pedido::

      cantidad_extra = cantidad_pedido - cantidad_eoq   (0 si no se subió)

* Ahorro bruto, solo si el pedido resultante accede al descuento::

      ahorro_bruto = cantidad_pedido * precio_unitario * (descuento_pct / 100)
                     (0 si el producto no tiene descuento)

* Costo extra de mantener el inventario adicional, valorado **por un periodo**
  (el exceso se compra una vez y se mantiene hasta el siguiente pedido: es la
  simplificación que declara la nota de implementación del PRD §10)::

      costo_extra_mantener = cantidad_extra * costo_unitario
                             * (costo_mantener_pct_anual / 100)
                             / periodos_por_año

  ``costo_mantener_pct_anual / 100`` es el mismo costo de mantener una unidad
  durante un año (``H``) que usa :mod:`src.motor.eoq_rop`, de modo que los dos
  módulos valoran el inventario con el mismo criterio; dividirlo entre
  ``periodos_por_año`` lo prorratea a un periodo (una doceava parte del anual
  con el default de 12). Como ``cantidad_extra`` es 0 en todas las filas sin
  subida al umbral, la fórmula se evalúa de una vez para todo el lote sin
  enmascararla.

* Resultado::

      ahorro_neto = ahorro_bruto - costo_extra_mantener

* Clasificación, contra un porcentaje del costo total del pedido::

      costo_total_pedido = cantidad_pedido * precio_unitario
      umbral_ahorro      = costo_total_pedido * (umbral_ahorro_pct / 100)
      estado = "Ahorro detectado"           si ahorro_neto >= umbral_ahorro
      estado = "Sin oportunidad adicional"  en caso contrario

Los nulos en ``cantidad_umbral_descuento`` o en ``descuento_pct`` significan
"el producto no tiene descuento por volumen" y **no** son un error: se tratan
producto por producto, así que un mismo lote puede mezclar productos con y sin
descuento. Un umbral o un descuento presente en solitario tampoco da acceso a
nada: hacen falta las dos columnas.

Comportamiento documentado de ``descuento_pct`` igual a 0: cuenta como
descuento declarado, así que sube el pedido al umbral si hace falta, con
``ahorro_bruto = 0`` y pagando el costo extra completo. Es consecuencia de la
asimetría deliberada del contrato (con o sin descuento, la cantidad pedida
nunca baja del EOQ: no se pide menos para "no ganar" el descuento) y no se
corrige aquí: un 0 es un descuento declarado por el dato, mientras que el dato
ausente es el nulo.

La comparación final se hace con la tolerancia :data:`TOLERANCIA_AHORRO` (1e-9),
igual que :data:`~src.motor.proveedor.TOLERANCIA_SCORE`,
:data:`~src.motor.xyz.TOLERANCIA_CV` y :data:`~src.motor.abc.TOLERANCIA_PCT`:
absorbe el ruido de punto flotante de una frontera exacta, donde ``ahorro_neto``
y ``umbral_ahorro`` son matemáticamente iguales pero su representación en
float64 deja al ahorro unas billonésimas por debajo. La tolerancia es holgada
frente a ese ruido (del orden de 1e-12) y despreciable frente a las diferencias
que importan (centavos): la consecuencia deliberada es que una diferencia real
menor que 1e-9 también se cuenta como "Ahorro detectado".

El módulo no agrupa: cada fila de entrada produce una fila de salida, así que un
``producto_id`` repetido aparecería repetido (el schema garantiza una fila por
producto). El orden de las filas de salida es por ``producto_id`` ascendente.

Este módulo concreta el criterio 6 de ``MVP.md`` (sección 10) en tres puntos que
su fórmula abreviada no fija y que se resolvieron a propósito: (1) el pedido se
sube al umbral para acceder al descuento, porque el criterio evalúa la
oportunidad de ahorro *por volumen*; (2) los porcentajes se dividen entre 100
(``5`` es 5 %), coherente con el resto del motor; y (3) el costo extra de
mantener se prorratea a un periodo dividiéndolo entre ``periodos_por_año``,
coherente con la nota de implementación del PRD que asume el exceso mantenido un
periodo completo.

El umbral de decisión es un parámetro de :func:`calcular_ahorro` y su valor por
defecto se lee de :data:`src.config.PARAMETROS_DEFAULT`
(``ahorro_neto_min_pct`` = 3.0), la fuente única de verdad de la tabla
``parametros_configuracion`` (db/schema.sql); este módulo no guarda una copia
local del valor. La parametrización no cambia la unidad: el umbral sigue siendo
un **porcentaje** del costo total del pedido (3.0 es 3 %, no 0.03), así que
dentro de la función se divide entre 100 igual que los demás ``*_pct`` del
motor.

El número de periodos por año y las etiquetas de estado siguen viviendo en
constantes de módulo (:data:`PERIODOS_POR_AÑO_DEFAULT`,
:data:`ESTADO_AHORRO` y :data:`ESTADO_SIN_OPORTUNIDAD`): no están en la tabla de
configuración, así que no son parámetros configurables y se quedan como fuente
única de verdad de sus valores.

El orden de los parámetros de :func:`calcular_ahorro` es el histórico
(``datos``, ``umbral_ahorro_pct``, ``periodos_por_año``): parametrizar el umbral
no mueve ninguna posición, de modo que las llamadas posicionales existentes
siguen funcionando igual (ver Notas del docstring de la función).
"""

import math

import numpy as np
import pandas as pd

from src.config import PARAMETROS_DEFAULT

__all__ = ["calcular_ahorro"]

# Columnas mínimas que debe traer el DataFrame de entrada. 'producto_id' viene
# de productos/producto_proveedor; 'precio_unitario',
# 'cantidad_umbral_descuento' y 'descuento_pct' de producto_proveedor;
# 'cantidad_eoq' de eoq_rop.py; 'costo_unitario' y 'costo_mantener_pct_anual' de
# productos.
COLUMNAS_REQUERIDAS: tuple[str, ...] = (
    "producto_id",
    "precio_unitario",
    "cantidad_umbral_descuento",
    "descuento_pct",
    "cantidad_eoq",
    "costo_unitario",
    "costo_mantener_pct_anual",
)

# Periodos que tiene un año, para prorratear el costo de mantener el exceso de
# inventario a un solo periodo. Mismo default, mismo nombre y mismo significado
# que en eoq_rop.py, para que los dos módulos midan el tiempo en las mismas
# unidades: con 12 (periodos mensuales) el costo extra es una doceava parte del
# anual. Esta constante sigue siendo la fuente única de verdad del valor: el
# número de periodos por año no está en la tabla de configuración, así que no es
# un parámetro configurable (a diferencia del umbral de ahorro), igual que en
# eoq_rop.py.
PERIODOS_POR_AÑO_DEFAULT: int = 12

# El umbral de decisión no vive aquí: es un parámetro de :func:`calcular_ahorro`
# y su fuente única de verdad es src.config.PARAMETROS_DEFAULT
# ('ahorro_neto_min_pct' = 3.0), de donde se lee el default de la firma. No se
# guarda una copia local del valor, para que un cambio de configuración se
# haga en un solo lugar (mismo criterio que abc.py, xyz.py, demanda.py y
# proveedor.py al parametrizarse). Ojo con la unidad: el valor está en
# porcentaje (3.0 = 3 %), igual que la constante que sustituye.

# Tolerancia al comparar el ahorro neto con el umbral de decisión. Absorbe el
# ruido de punto flotante en fronteras exactas (p. ej. un ahorro neto
# matemáticamente igual al umbral que en float64 queda unas billonésimas por
# debajo) sin alterar comparaciones con diferencias significativas. Mismo
# criterio que TOLERANCIA_PCT en abc.py, TOLERANCIA_CV en xyz.py y
# TOLERANCIA_SCORE en proveedor.py.
TOLERANCIA_AHORRO: float = 1e-9

# Etiquetas de estado del criterio 6. Constantes de módulo para que un cambio de
# redacción se haga en un solo lugar.
ESTADO_AHORRO: str = "Ahorro detectado"
ESTADO_SIN_OPORTUNIDAD: str = "Sin oportunidad adicional"


def calcular_ahorro(
    datos: pd.DataFrame,
    umbral_ahorro_pct: float = PARAMETROS_DEFAULT["ahorro_neto_min_pct"],
    periodos_por_año: int = PERIODOS_POR_AÑO_DEFAULT,
) -> pd.DataFrame:
    """
    Calcula la oportunidad de ahorro por descuento de volumen por producto.

    Args:
        datos: DataFrame con una fila por producto. Columnas requeridas:
            - producto_id
            - precio_unitario: precio del proveedor (float >= 0)
            - cantidad_umbral_descuento: cantidad mínima para acceder al
              descuento (float >= 0 o None)
            - descuento_pct: % de descuento si se supera el umbral
              (float entre 0 y 100, o None)
            - cantidad_eoq: EOQ calculado por eoq_rop.py (float >= 0)
            - costo_unitario: costo por unidad (float >= 0)
            - costo_mantener_pct_anual: % anual de mantener (float >= 0)
        umbral_ahorro_pct: porcentaje mínimo del costo total del pedido que
            debe representar el ahorro neto para considerarse "Ahorro
            detectado". Se expresa en **porcentaje**, no en fracción: 3.0 es
            3 % (no 0.03), y por eso dentro de la función se divide entre 100
            (``umbral_ahorro = costo_total_pedido * (umbral_ahorro_pct / 100)``).
            Default 3.0, leído de
            ``config.PARAMETROS_DEFAULT["ahorro_neto_min_pct"]`` (fuente única
            de verdad: ``parametros_configuracion``, db/schema.sql). Debe ser
            un número >= 0 (no NaN).
        periodos_por_año: periodos que tiene un año, para prorratear el costo
            de mantener el exceso de inventario a un solo periodo. Default 12
            (periodos mensuales), igual que en eoq_rop.py. Debe ser un entero
            positivo. No es un parámetro configurable: no está en la tabla de
            configuración y vive en :data:`PERIODOS_POR_AÑO_DEFAULT`.

    Returns:
        DataFrame con una fila por producto, con columnas:
            - producto_id
            - cantidad_pedido: cantidad efectivamente sugerida
            - ahorro_bruto: ahorro por descuento antes del costo extra
            - costo_extra_mantener: costo del inventario adicional
            - ahorro_neto: ahorro_bruto - costo_extra_mantener
            - estado: "Ahorro detectado" o "Sin oportunidad adicional"
        El orden de las filas es por producto_id ascendente.

    Reglas:
        - Si el producto no tiene descuento (umbral o descuento nulos):
            cantidad_pedido = cantidad_eoq, ahorro_bruto = 0,
            costo_extra_mantener = 0, ahorro_neto = 0.
        - Si cantidad_eoq >= cantidad_umbral_descuento:
            cantidad_pedido = cantidad_eoq, cantidad_extra = 0,
            ahorro_bruto = cantidad_pedido * precio_unitario * (descuento/100).
        - Si cantidad_eoq < cantidad_umbral_descuento:
            cantidad_pedido = cantidad_umbral_descuento,
            cantidad_extra = cantidad_umbral_descuento - cantidad_eoq,
            ahorro_bruto = cantidad_pedido * precio_unitario * (descuento/100),
            costo_extra_mantener = cantidad_extra * costo_unitario
                                   * (costo_mantener_pct_anual / 100)
                                   / periodos_por_año.
        - ahorro_neto = ahorro_bruto - costo_extra_mantener
        - costo_total_pedido = cantidad_pedido * precio_unitario
        - umbral_ahorro = costo_total_pedido * (umbral_ahorro_pct / 100)
        - estado = "Ahorro detectado" si ahorro_neto >= umbral_ahorro,
          sino "Sin oportunidad adicional".
        - La precedencia de la primera regla es explícita: un producto sin
          descuento nunca entra en las dos siguientes, aunque su
          cantidad_umbral_descuento sea NaN y la comparación sea False.
        - La cantidad pedida nunca baja del EOQ: el módulo solo evalúa subir el
          pedido al umbral, nunca pedir menos para no ganar el descuento.

    Notas:
        - La función es pura: no accede a red, DB ni archivos. No imprime
          ni registra nada.
        - No modifica el DataFrame de entrada.
        - La salida es un DataFrame nuevo, con RangeIndex desde 0.
        - Se asume que los datos cumplen los rangos del schema; no se
          validan rangos aquí.
        - El umbral es un parámetro con default: quien no lo pase obtiene
          exactamente el comportamiento histórico (3 % del costo del pedido),
          porque su default se lee de :data:`src.config.PARAMETROS_DEFAULT` y
          este módulo no guarda copias locales del valor.
        - El umbral se interpreta en porcentaje (3.0 = 3 %), no en fracción:
          pasar 0.03 equivale a exigir un 0.03 % del costo del pedido, no un
          3 % (con 0.03 casi cualquier ahorro neto positivo se clasifica como
          "Ahorro detectado"). Es el mismo contrato de ``descuento_pct`` y
          ``costo_mantener_pct_anual``, que también llegan como porcentaje.
        - La firma mantiene el orden histórico de sus parámetros (``datos``,
          ``umbral_ahorro_pct``, ``periodos_por_año``): el umbral ya ocupaba la
          segunda posición, así que un llamador que lo pase posicionalmente
          (``calcular_ahorro(datos, 5.0)``) sigue funcionando igual; no se
          reordena la firma para no romper llamadas existentes.
        - Orden de ejecución: (1) validar los parámetros escalares (el umbral y
          periodos_por_año, en el orden de la firma), (2) validar columnas,
          (3) si está vacío devolver vacío, (4) si hay filas calcular.
        - Los nulos en cantidad_umbral_descuento o descuento_pct indican
          "sin descuento por volumen" y NO son un error.
        - Se usa una tolerancia (TOLERANCIA_AHORRO = 1e-9) para absorber
          errores de punto flotante en la comparación
          ahorro_neto >= umbral_ahorro.
        - Con umbral_ahorro_pct = 0 el umbral de decisión es 0, así que un
          producto sin descuento (ahorro_neto = 0) queda como "Ahorro
          detectado": es consecuencia de la regla, no un caso especial.
        - Se adopta la lectura "subir el pedido al umbral para acceder al
          descuento": en MVP.md §10 la condición "solo si cantidad_EOQ >=
          cantidad_umbral_descuento" se lee como el caso que ya accede al
          descuento sin tocar la cantidad, no como una prohibición de subirla
          (el criterio evalúa la oportunidad de ahorro por volumen).
        - El costo extra de mantener se prorratea a un periodo dividiéndolo
          entre periodos_por_año: el exceso de inventario se mantiene hasta el
          siguiente pedido, no un año completo (PRD §10, nota de
          implementación). Con el default de 12, el costo extra anual se
          divide entre 12.
        - descuento_pct = 0 se trata como descuento declarado: sube el pedido al
          umbral si hace falta, con ahorro_bruto = 0 y pagando el costo extra.
          Es un comportamiento documentado y deliberado, no un descuido: el
          dato ausente es el nulo, no el 0.

    Raises:
        ValueError: si al DataFrame le falta alguna columna requerida,
            tenga o no filas.
        ValueError: si umbral_ahorro_pct no es un número >= 0 (incluye NaN).
        ValueError: si periodos_por_año no es un entero positivo.
    """

    # Los parámetros escalares se validan primero, en el orden de la firma: es
    # la única validación que no depende de los datos y por lo tanto aplica
    # incluso si la entrada está vacía.
    _verificar_umbral_ahorro(umbral_ahorro_pct)
    _verificar_entero_positivo("periodos_por_año", periodos_por_año)

    tabla: pd.DataFrame = datos.copy()

    # Validación estricta: se hace antes de cualquier atajo por DataFrame
    # vacío, de modo que un DataFrame sin filas y sin columnas también falla.
    _verificar_columnas(tabla)

    # Si no hay filas no hay nada que calcular: se devuelve la salida vacía con
    # las columnas y dtypes correctos.
    if tabla.empty:
        return _resultado_vacio()

    producto_id: np.ndarray = tabla["producto_id"].to_numpy(dtype=object)
    precio_unitario: np.ndarray = tabla["precio_unitario"].to_numpy(dtype="float64")
    cantidad_umbral: np.ndarray = tabla["cantidad_umbral_descuento"].to_numpy(
        dtype="float64"
    )
    descuento_pct: np.ndarray = tabla["descuento_pct"].to_numpy(dtype="float64")
    cantidad_eoq: np.ndarray = tabla["cantidad_eoq"].to_numpy(dtype="float64")
    costo_unitario: np.ndarray = tabla["costo_unitario"].to_numpy(dtype="float64")
    costo_mantener_pct: np.ndarray = tabla["costo_mantener_pct_anual"].to_numpy(
        dtype="float64"
    )

    # Un producto tiene descuento por volumen solo si están las dos columnas: un
    # umbral sin descuento (o al revés) no da acceso a nada. Los nulos de una
    # columna numérica llegan como NaN, así que la prueba es isnan y no 'is
    # None'.
    tiene_descuento: np.ndarray = ~np.isnan(cantidad_umbral) & ~np.isnan(descuento_pct)

    # Solo se sube el pedido cuando el EOQ natural se queda por debajo del
    # umbral. Con umbral nulo la comparación es False y 'tiene_descuento' ya
    # descarta esas filas, de modo que el NaN nunca se propaga al resultado.
    sube_al_umbral: np.ndarray = tiene_descuento & (cantidad_eoq < cantidad_umbral)

    cantidad_pedido: np.ndarray = np.where(
        sube_al_umbral, cantidad_umbral, cantidad_eoq
    )
    cantidad_extra: np.ndarray = np.where(
        sube_al_umbral, cantidad_umbral - cantidad_eoq, 0.0
    )

    # Acceso al descuento: el producto lo tiene y la cantidad sugerida (por EOQ
    # o por subida al umbral) alcanza la cantidad mínima.
    accede_descuento: np.ndarray = tiene_descuento & (
        cantidad_pedido >= cantidad_umbral
    )

    # Ahorro bruto: el descuento se aplica sobre el pedido completo. Donde no se
    # accede al descuento vale 0, sin propagar el NaN del umbral nulo.
    ahorro_bruto: np.ndarray = np.where(
        accede_descuento,
        cantidad_pedido * precio_unitario * (descuento_pct / 100.0),
        0.0,
    )

    # Costo extra de mantener: 'cantidad_extra' ya es 0 en las filas que no
    # subieron el pedido (y en las que no tienen descuento), así que la fórmula
    # se evalúa de una vez para todo el lote. Se prorratea a un periodo
    # dividiendo entre periodos_por_año: el exceso de inventario se mantiene
    # hasta el siguiente pedido, no un año completo.
    costo_extra_mantener: np.ndarray = (
        cantidad_extra
        * costo_unitario
        * (costo_mantener_pct / 100.0)
        / periodos_por_año
    )

    ahorro_neto: np.ndarray = ahorro_bruto - costo_extra_mantener

    # Base del umbral de decisión: el costo del pedido sugerido. El umbral llega
    # en PORCENTAJE (3.0 = 3 %), así que aquí se divide entre 100 igual que
    # descuento_pct y costo_mantener_pct: la parametrización del módulo no
    # cambió la unidad del parámetro.
    costo_total_pedido: np.ndarray = cantidad_pedido * precio_unitario
    umbral_ahorro: np.ndarray = costo_total_pedido * (umbral_ahorro_pct / 100.0)

    # Se resta TOLERANCIA_AHORRO al umbral para absorber el ruido de punto
    # flotante (p. ej. un ahorro neto matemáticamente igual al umbral que en
    # float64 queda unas billonésimas por debajo) sin mover ninguna frontera con
    # diferencia significativa.
    estado: np.ndarray = np.select(
        [ahorro_neto >= umbral_ahorro - TOLERANCIA_AHORRO],
        [ESTADO_AHORRO],
        default=ESTADO_SIN_OPORTUNIDAD,
    )

    resultado: pd.DataFrame = pd.DataFrame(
        {
            "producto_id": pd.Series(producto_id, dtype=object),
            "cantidad_pedido": pd.Series(cantidad_pedido, dtype="float64"),
            "ahorro_bruto": pd.Series(ahorro_bruto, dtype="float64"),
            "costo_extra_mantener": pd.Series(costo_extra_mantener, dtype="float64"),
            "ahorro_neto": pd.Series(ahorro_neto, dtype="float64"),
            "estado": pd.Series(estado, dtype=object),
        }
    )

    # Orden determinista: producto_id ascendente. Se ordena explícitamente para
    # que la garantía no dependa del orden de entrada. 'mergesort' es estable,
    # igual que en abc.py, xyz.py, demanda.py, eoq_rop.py y proveedor.py.
    return resultado.sort_values(by="producto_id", kind="mergesort").reset_index(
        drop=True
    )


def _resultado_vacio() -> pd.DataFrame:
    """Devuelve el resultado vacío, con las columnas y dtypes de la salida.

    Returns:
        DataFrame sin filas con las columnas producto_id (object),
        cantidad_pedido, ahorro_bruto, costo_extra_mantener y ahorro_neto
        (float64) y estado (object), y con un RangeIndex vacío.
    """
    return pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "cantidad_pedido": pd.Series(dtype="float64"),
            "ahorro_bruto": pd.Series(dtype="float64"),
            "costo_extra_mantener": pd.Series(dtype="float64"),
            "ahorro_neto": pd.Series(dtype="float64"),
            "estado": pd.Series(dtype=object),
        }
    )


def _verificar_umbral_ahorro(umbral: object) -> None:
    """Valida que el umbral de ahorro sea un número no negativo.

    Args:
        umbral: valor de `umbral_ahorro_pct` tal como llegó del llamador.

    Raises:
        ValueError: si `umbral` no es un número (int o float), es NaN o es
            negativo. Un int se acepta porque se interpreta igual que el float
            (3 == 3.0); los booleanos se rechazan explícitamente porque
            ``isinstance(True, int)`` es True pero True no es un porcentaje.
    """
    if isinstance(umbral, bool) or not isinstance(umbral, (int, float)):
        raise ValueError(
            "calcular_ahorro: 'umbral_ahorro_pct' debe ser un número >= 0; se "
            f"recibió {umbral!r} ({type(umbral).__name__})."
        )
    # NaN pasa la comprobación de tipo (es un float) pero no es un umbral
    # válido: toda comparación con él es False, así que clasificaría el lote
    # entero como "Sin oportunidad adicional" en silencio.
    if math.isnan(umbral):
        raise ValueError(
            "calcular_ahorro: 'umbral_ahorro_pct' debe ser un número >= 0; se "
            "recibió nan."
        )
    if umbral < 0:
        raise ValueError(
            "calcular_ahorro: 'umbral_ahorro_pct' debe ser un número >= 0; se "
            f"recibió {umbral}."
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
            Python, pero True no es un número de periodos. Mismo criterio que
            ``_verificar_entero_positivo`` en eoq_rop.py.
    """
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError(
            f"calcular_ahorro: '{nombre}' debe ser un entero positivo; se "
            f"recibió {valor!r} ({type(valor).__name__})."
        )
    if valor < 1:
        raise ValueError(
            f"calcular_ahorro: '{nombre}' debe ser un entero positivo; se "
            f"recibió {valor}."
        )


def _verificar_columnas(datos: pd.DataFrame) -> None:
    """Valida que el DataFrame traiga las columnas requeridas.

    Args:
        datos: DataFrame de entrada de :func:`calcular_ahorro`.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna for columna in COLUMNAS_REQUERIDAS if columna not in datos.columns
    ]
    if faltantes:
        raise ValueError(
            "calcular_ahorro requiere las columnas "
            f"{', '.join(COLUMNAS_REQUERIDAS)}; faltan: {', '.join(faltantes)}."
        )

