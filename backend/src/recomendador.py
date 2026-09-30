"""Orquestación del motor OR y persistencia de las recomendaciones de compra.

Este módulo es el primero que coordina datos de varias fuentes y, de forma
opcional, escribe en Supabase. Expone tres funciones con responsabilidades
separadas:

* :func:`calcular_recomendaciones` -- función **pura**: recibe cuatro DataFrames
  (más un dict opcional de parámetros de configuración)
  y devuelve un DataFrame. Orquesta los seis módulos del motor, no accede a red,
  base de datos ni archivos, no imprime ni registra nada y no modifica las
  entradas. Es la parte testeable.
* :func:`generar_recomendaciones` -- lee las cinco tablas de Supabase (las cuatro
  de datos y ``parametros_configuracion``),
  normaliza los nombres de columna y delega el cálculo en
  :func:`calcular_recomendaciones`. Solo hace E/S: no contiene lógica de
  negocio.
* :func:`guardar_recomendaciones` -- escribe las recomendaciones en la tabla
  ``recomendaciones`` y **devuelve las filas insertadas**, con los ``id`` (uuid)
  que generó Supabase. Solo hace E/S: no calcula nada.

Convención de nombres de columna
--------------------------------
Las tablas de Supabase no son uniformes: ``productos`` y ``proveedores``
identifican sus filas con ``id`` y los proveedores guardan su descripción en
``nombre``. Las funciones del motor, en cambio, esperan ``producto_id``,
``proveedor_id`` y ``proveedor_nombre``. El renombre se hace en
:func:`generar_recomendaciones`, justo después de leer Supabase, de modo que
:func:`calcular_recomendaciones` recibe siempre los nombres que el motor espera
(y sus tests los construyen directamente con esos nombres).

Parámetros de configuración
---------------------------
Los umbrales del motor (cortes ABC, ventana de demanda, CV de confianza, cortes
de score de proveedor y umbral de ahorro) llegan en el parámetro ``parametros``
de :func:`calcular_recomendaciones`, que espera las claves de
:data:`src.config.PARAMETROS_DEFAULT`; ``None`` significa "usar los defaults del
sistema". Esta función **no** los lee de Supabase: los carga
:func:`generar_recomendaciones` con :func:`src.config.cargar_parametros` y los
pasa ya resueltos, de modo que la parte calculable sigue siendo pura y testeable
sin red. Los tres parámetros de :mod:`src.motor.eoq_rop` (``periodos_por_año``,
``dias_por_periodo`` y ``margen_seguridad_pct``) no están en la tabla de
configuración y por eso siguen siendo argumentos propios de este módulo.

Algoritmo de :func:`calcular_recomendaciones`
--------------------------------------------
1. **Productos válidos**: los que tienen al menos :data:`~src.motor.xyz.MIN_PERIODOS`
   filas de historial (2, el mínimo para calcular una desviación estándar
   muestral), al menos una fila en ``producto_proveedor`` y un coeficiente de
   variación calculable. El resto se descarta en silencio (ver "Casos borde").
2. **CV calculable**: :func:`src.motor.xyz.clasificar_xyz` devuelve ``cv`` y
   ``clase_xyz`` nulos cuando la demanda media es 0. Esos productos se excluyen
   (la tabla ``recomendaciones`` declara ``cv_demanda`` y ``clase_xyz`` como
   ``not null``), así que la clasificación XYZ se calcula sobre los productos del
   paso 1 y de ahí sale también la lista definitiva de productos.
3. **Proveedor elegido por producto**: se puntúa a cada proveedor con
   :func:`src.motor.proveedor.calcular_score_proveedor` y, entre los proveedores
   de cada producto, se elige el de mayor score y, en caso de empate, el de menor
   precio. Queda un proveedor por producto.
4. **Métricas del motor** sobre los productos válidos: ABC, demanda estimada,
   EOQ / stock de seguridad / punto de reorden y ahorro por volumen. Los
   DataFrames que recibe cada módulo se filtran antes por los productos válidos,
   de modo que el motor nunca procesa un producto que se va a descartar después.
5. **Combinación** con ``pd.merge(..., how="inner")`` por ``producto_id``, más el
   dato auxiliar ``costo_total_pedido``.
6. **Urgencia** por riesgo de quiebre (marca, no filtra): ``Crítico`` si
   ``stock_actual <= stock_seguridad``, ``Atención`` si
   ``stock_seguridad < stock_actual <= punto_reorden`` y ``Sin riesgo`` si
   ``stock_actual > punto_reorden``.
7. **Orden**: urgencia (Crítico > Atención > Sin riesgo), luego
   ``ahorro_neto_estimado`` descendente y, como desempate final, ``producto_id``
   ascendente.

Columnas de la salida
---------------------
En este orden: ``producto_id``, ``proveedor_id``, ``proveedor_nombre``,
``nombre``, ``categoria``, ``clase_abc``, ``clase_xyz``, ``cv_demanda``
(el ``cv`` de :mod:`src.motor.xyz`), ``demanda_estimada``, ``cantidad_eoq``,
``stock_seguridad``, ``punto_reorden``, ``lead_time_dias``, ``precio_unitario``,
``score_proveedor``, ``cantidad_recomendada`` (el ``cantidad_pedido`` de
:mod:`src.motor.ahorro`), ``ahorro_neto_estimado`` (su ``ahorro_neto``),
``estado_ahorro`` (su ``estado``), ``stock_actual``, ``costo_unitario``,
``costo_ordenar``, ``costo_mantener_pct_anual``, ``ahorro_bruto``,
``costo_extra_mantener``, ``costo_total_pedido`` y ``urgencia``.

``cantidad_umbral_descuento`` y ``descuento_pct`` (los dos del proveedor
elegido) se añaden al final para que los insumos del criterio 6 de la rúbrica
sean visibles en la salida y para que esta quede trazable hasta los datos de
entrada (RF-05 y RF-08 de ``MVP.md`` §6): son las dos únicas columnas que
**pueden** contener valores nulos, y un nulo significa "el producto no tiene
descuento por volumen" (ver :mod:`src.motor.ahorro`). No forman parte de la
lista de la sección «Columnas de la salida».

Casos borde
-----------
* Producto con menos de 2 filas de historial: se excluye de la salida.
* Producto sin filas en ``producto_proveedor``: se excluye de la salida.
* Producto cuyo proveedor no está en ``proveedores`` (imposible con la clave
  foránea del schema): sus relaciones se descartan y el producto se excluye si no
  le queda ninguna.
* Producto con 2 o más periodos pero con demanda media 0 (todos sus periodos en
  0): :mod:`src.motor.xyz` no puede calcular su CV (división por cero) y devuelve
  ``None``; el producto se excluye igual que los anteriores, porque la tabla
  ``recomendaciones`` declara ``cv_demanda`` y ``clase_xyz`` como ``not null``.
  Gracias a esa exclusión, :data:`COLUMNAS_NO_NULAS` no necesita incluirlas.
* Producto con ``costo_unitario == 0`` o ``costo_mantener_pct_anual == 0``: el
  ``ValueError`` de :func:`src.motor.eoq_rop.calcular_eoq_rop` (H == 0) se
  propaga. El llamador debe garantizar las precondiciones del motor.
* Ningún producto válido: se devuelve un DataFrame vacío con las columnas y los
  dtypes de la salida.
* Se asume que ``productos`` y ``proveedores`` traen una fila por identificador
  (el schema los declara clave primaria); filas repetidas producirían filas
  repetidas en la salida.
* Entradas vacías con las columnas requeridas se comportan como "sin productos
  válidos" salvo por los parámetros escalares, que valida el motor.

Contrato de errores
-------------------
El módulo **propaga** los ``ValueError`` del motor en lugar de capturarlos: un
dato que el schema admite pero que el motor no puede calcular (H == 0, por
ejemplo) es un problema del llamador, no algo que este módulo deba esconder.
"""

import numpy as np
import pandas as pd

from src.config import PARAMETROS_DEFAULT, cargar_parametros
from src.motor.abc import clasificar_abc
from src.motor.ahorro import calcular_ahorro
from src.motor.demanda import estimar_demanda
from src.motor.eoq_rop import (
    DIAS_POR_PERIODO_DEFAULT,
    MARGEN_SEGURIDAD_PCT_DEFAULT,
    PERIODOS_POR_AÑO_DEFAULT,
    calcular_eoq_rop,
)
from src.motor.proveedor import calcular_score_proveedor
from src.motor.xyz import MIN_PERIODOS, clasificar_xyz

__all__ = [
    "calcular_recomendaciones",
    "generar_recomendaciones",
    "guardar_recomendaciones",
]

# Etiquetas de urgencia por riesgo de quiebre (criterio 1 de la rúbrica).
# Constantes de módulo para que un cambio de redacción se haga en un solo lugar.
URGENCIA_CRITICO: str = "Crítico"
URGENCIA_ATENCION: str = "Atención"
URGENCIA_SIN_RIESGO: str = "Sin riesgo"

# Jerarquía de negocio de la urgencia, de mayor a menor prioridad. Se usa para
# construir la columna categórica ordenada con la que se ordena la salida: sin
# ella, 'Atención' quedaría después de 'Crítico' por orden alfabético.
ORDEN_URGENCIA: list[str] = [
    URGENCIA_CRITICO,
    URGENCIA_ATENCION,
    URGENCIA_SIN_RIESGO,
]

# Columnas que debe traer cada DataFrame de entrada de
# :func:`calcular_recomendaciones`. Son los nombres que el motor espera, ya
# normalizados por :func:`generar_recomendaciones`.
COLUMNAS_PRODUCTOS: tuple[str, ...] = (
    "producto_id",
    "nombre",
    "categoria",
    "costo_unitario",
    "stock_actual",
    "costo_ordenar",
    "costo_mantener_pct_anual",
)

COLUMNAS_PROVEEDORES: tuple[str, ...] = (
    "proveedor_id",
    "proveedor_nombre",
    "cumplimiento_entrega_pct",
    "tasa_defectos_pct",
)

COLUMNAS_PRODUCTO_PROVEEDOR: tuple[str, ...] = (
    "producto_id",
    "proveedor_id",
    "precio_unitario",
    "lead_time_dias",
    "cantidad_umbral_descuento",
    "descuento_pct",
)

COLUMNAS_HISTORIAL: tuple[str, ...] = (
    "producto_id",
    "periodo",
    "cantidad_demandada",
)

# Columnas del proveedor elegido por producto (paso 2), en el orden en que se
# documentan. Es la única fila de proveedor que sobrevive por producto.
COLUMNAS_PROVEEDOR_ELEGIDO: tuple[str, ...] = (
    "producto_id",
    "proveedor_id",
    "proveedor_nombre",
    "precio_unitario",
    "lead_time_dias",
    "cantidad_umbral_descuento",
    "descuento_pct",
    "cumplimiento_entrega_pct",
    "tasa_defectos_pct",
    "score_proveedor",
)

# Columnas de la tabla 'recomendaciones' que escribe
# :func:`guardar_recomendaciones`. 'id', 'fecha_generacion' y 'estado' los pone
# Supabase por default (now() y 'pendiente'), así que no se envían.
COLUMNAS_RECOMENDACIONES: tuple[str, ...] = (
    "producto_id",
    "proveedor_id",
    "demanda_estimada",
    "cv_demanda",
    "punto_reorden",
    "stock_seguridad",
    "cantidad_eoq",
    "cantidad_recomendada",
    "clase_abc",
    "clase_xyz",
    "lead_time_dias",
    "precio_unitario",
    "ahorro_neto_estimado",
)

# Columnas de la salida que no admiten valores nulos. Se verifican después de
# los merges: un nulo aquí significa que algún módulo del motor no pudo calcular
# el producto (o que un dato de entrada faltaba), y es un error, no una fila a
# descartar.
COLUMNAS_NO_NULAS: tuple[str, ...] = (
    "producto_id",
    "proveedor_id",
    "clase_abc",
    "clase_xyz",
    "demanda_estimada",
    "cantidad_eoq",
    "stock_seguridad",
    "punto_reorden",
    "cantidad_recomendada",
    "ahorro_neto_estimado",
)

# Columnas de la salida, en orden. 'cantidad_umbral_descuento' y 'descuento_pct'
# van al final y son las dos únicas que pueden traer nulos (producto sin
# descuento por volumen).
COLUMNAS_SALIDA: tuple[str, ...] = (
    "producto_id",
    "proveedor_id",
    "proveedor_nombre",
    "nombre",
    "categoria",
    "clase_abc",
    "clase_xyz",
    "cv_demanda",
    "demanda_estimada",
    "cantidad_eoq",
    "stock_seguridad",
    "punto_reorden",
    "lead_time_dias",
    "precio_unitario",
    "score_proveedor",
    "cantidad_recomendada",
    "ahorro_neto_estimado",
    "estado_ahorro",
    "stock_actual",
    "costo_unitario",
    "costo_ordenar",
    "costo_mantener_pct_anual",
    "ahorro_bruto",
    "costo_extra_mantener",
    "costo_total_pedido",
    "urgencia",
    "cantidad_umbral_descuento",
    "descuento_pct",
)


def calcular_recomendaciones(
    productos: pd.DataFrame,
    proveedores: pd.DataFrame,
    producto_proveedor: pd.DataFrame,
    historial_demanda: pd.DataFrame,
    parametros: dict[str, float] | None = None,
    periodos_por_año: int = PERIODOS_POR_AÑO_DEFAULT,
    dias_por_periodo: int = DIAS_POR_PERIODO_DEFAULT,
    margen_seguridad_pct: float = MARGEN_SEGURIDAD_PCT_DEFAULT,
) -> pd.DataFrame:
    """
    Calcula una recomendación de compra por producto válido, con su proveedor.

    Args:
        productos: catálogo, con las columnas de :data:`COLUMNAS_PRODUCTOS`
            (``producto_id``, ``nombre``, ``categoria``, ``costo_unitario``,
            ``stock_actual``, ``costo_ordenar``, ``costo_mantener_pct_anual``).
        proveedores: catálogo de proveedores, con las columnas de
            :data:`COLUMNAS_PROVEEDORES` (``proveedor_id``,
            ``proveedor_nombre``, ``cumplimiento_entrega_pct``,
            ``tasa_defectos_pct``).
        producto_proveedor: relación producto-proveedor, con las columnas de
            :data:`COLUMNAS_PRODUCTO_PROVEEDOR` (``producto_id``,
            ``proveedor_id``, ``precio_unitario``, ``lead_time_dias``,
            ``cantidad_umbral_descuento`` y ``descuento_pct``, estas dos últimas
            anulables).
        historial_demanda: historial en formato largo, con las columnas de
            :data:`COLUMNAS_HISTORIAL` (``producto_id``, ``periodo``,
            ``cantidad_demandada``).
        parametros: dict[str, float] | None = None. Diccionario con los
            parámetros de configuración. Si es None, se usa
            :data:`src.config.PARAMETROS_DEFAULT`. Las claves esperadas son las
            de :data:`src.config.PARAMETROS_DEFAULT`: ``abc_clase_a_pct`` y
            ``abc_clase_b_pct`` (cortes de
            :func:`src.motor.abc.clasificar_abc`), ``demanda_ventana_default``
            (ventana de :func:`src.motor.demanda.estimar_demanda`, convertida a
            ``int`` porque el dict trae floats), ``cv_confianza_alta`` y
            ``cv_confianza_media`` (cortes de
            :func:`src.motor.xyz.clasificar_xyz`), ``score_proveedor_confiable``
            y ``score_proveedor_riesgoso`` (cortes de
            :func:`src.motor.proveedor.calcular_score_proveedor`) y
            ``ahorro_neto_min_pct`` (umbral de
            :func:`src.motor.ahorro.calcular_ahorro`). Las claves
            ``eoq_min_pct`` y ``eoq_max_pct`` también vienen en el dict, pero
            las consume :mod:`src.evaluador`, no este módulo.
        periodos_por_año: periodos que tiene un año, para anualizar la demanda y
            prorratear el costo de mantener el exceso de inventario. Default
            :data:`src.motor.eoq_rop.PERIODOS_POR_AÑO_DEFAULT` (12, periodos
            mensuales). Se pasa el mismo valor a
            :func:`src.motor.eoq_rop.calcular_eoq_rop` y a
            :func:`src.motor.ahorro.calcular_ahorro` para que los dos módulos
            midan el tiempo en las mismas unidades (deuda técnica declarada en
            ``PENDIENTES.md``).
        dias_por_periodo: días que tiene un periodo, para el stock de seguridad y
            el punto de reorden. Default
            :data:`src.motor.eoq_rop.DIAS_POR_PERIODO_DEFAULT` (30).
        margen_seguridad_pct: margen sobre el consumo esperado durante el lead
            time. Default
            :data:`src.motor.eoq_rop.MARGEN_SEGURIDAD_PCT_DEFAULT` (0.20, 20 %).

    Returns:
        DataFrame con una fila por producto válido y las columnas de
        :data:`COLUMNAS_SALIDA`, ordenado por urgencia (Crítico primero, luego
        Atención, luego Sin riesgo), luego por ``ahorro_neto_estimado``
        descendente y luego por ``producto_id`` ascendente. La columna
        ``urgencia`` es un ``pd.Categorical`` ordenado con las categorías de
        :data:`ORDEN_URGENCIA`; como 'Crítico' es la categoría *menor* de esa
        jerarquía, el orden pedido se obtiene con ``ascending=True`` sobre la
        categórica (con ``ascending=False`` saldría al revés).

    Reglas:
        - Un producto entra en la salida si aparece en ``historial_demanda`` con
          al menos :data:`~src.motor.xyz.MIN_PERIODOS` filas, tiene al menos una
          fila en ``producto_proveedor`` y su coeficiente de variación es
          calculable (demanda media mayor que 0). Los productos que no cumplen se
          descartan en silencio: son los que el motor no puede calcular (sin CV,
          sin proveedor al que pedirle, sin clase XYZ) y no tiene sentido
          reportarlos como recomendación.
        - El proveedor elegido es el de mayor score; si hay empate, el de menor
          ``precio_unitario``. Si score y precio empatan, gana el que aparece
          primero en ``producto_proveedor``.
        - ``urgencia`` marca riesgo de quiebre (``stock_actual`` contra
          ``stock_seguridad`` y ``punto_reorden``); no filtra filas.
        - ``cantidad_umbral_descuento`` y ``descuento_pct`` pueden ser NaN
          (producto sin descuento por volumen): es válido y esperado.

    Notas:
        - La función es pura: no accede a red, DB ni archivos, no imprime ni
          registra nada y no modifica los DataFrames de entrada ni el dict
          ``parametros``. La lectura de los parámetros desde Supabase es
          responsabilidad de :func:`generar_recomendaciones`.
        - La salida es un DataFrame nuevo, con RangeIndex desde 0.
        - Toda combinación de resultados se hace con ``how="inner"`` por
          ``producto_id``: la salida solo contiene productos que sobrevivieron a
          todos los módulos del motor.
        - ``cv_demanda`` y ``clase_xyz`` nunca son nulos en la salida: los
          productos sin CV calculable se excluyen (ver Reglas), así que no hace
          falta que :data:`COLUMNAS_NO_NULAS` las incluya para cumplir el
          ``not null`` de la tabla ``recomendaciones``.
        - ``parametros`` solo aporta los ocho umbrales del motor listados en
          Args; ``periodos_por_año``, ``dias_por_periodo`` y
          ``margen_seguridad_pct`` siguen siendo argumentos propios, con los
          defaults de :mod:`src.motor.eoq_rop`
          (:data:`~src.motor.eoq_rop.PERIODOS_POR_AÑO_DEFAULT`,
          :data:`~src.motor.eoq_rop.DIAS_POR_PERIODO_DEFAULT` y
          :data:`~src.motor.eoq_rop.MARGEN_SEGURIDAD_PCT_DEFAULT`), porque no
          están en ``parametros_configuracion`` (``eoq_rop.py`` no se configura
          desde la tabla).
        - Los ``ValueError`` del motor se propagan sin capturarlos. El llamador
          debe asegurar las precondiciones del motor, en particular
          ``costo_unitario > 0`` y ``costo_mantener_pct_anual > 0`` para todo
          producto (H > 0 en :mod:`src.motor.eoq_rop`).

    Raises:
        KeyError: si ``parametros`` no trae alguna de las claves de umbral que
            este módulo indexa. No se verifica aquí con
            :func:`src.config.verificar_parametros`: cuando el dict viene de
            Supabase, :func:`src.config.cargar_parametros` ya lo verifica, y un
            dict incompleto pasado a mano debe fallar, no completarse en
            silencio con los defaults.
        ValueError: si a alguno de los cuatro DataFrames le falta una columna
            requerida.
        ValueError: si tras los merges alguna columna de
            :data:`COLUMNAS_NO_NULAS` contiene nulos; el mensaje indica qué
            columnas y qué ``producto_id``.
        ValueError: cualquier ``ValueError`` validado por los módulos del motor
            (parámetros escalares fuera de rango, H == 0, etc.), propagado tal
            cual.
    """

    # Los parámetros de configuración se resuelven antes de llamar a cualquier
    # módulo del motor: None significa "usar los defaults del sistema". La
    # función no los lee de Supabase (sigue siendo pura); los carga
    # generar_recomendaciones y llegan ya resueltos o como None.
    if parametros is None:
        parametros = PARAMETROS_DEFAULT

    # Validación mínima de columnas: es lo primero, para no llamar al motor con
    # datos incompletos y para que el error señale el DataFrame culpable.
    _verificar_columnas(productos, COLUMNAS_PRODUCTOS, "productos")
    _verificar_columnas(proveedores, COLUMNAS_PROVEEDORES, "proveedores")
    _verificar_columnas(
        producto_proveedor, COLUMNAS_PRODUCTO_PROVEEDOR, "producto_proveedor"
    )
    _verificar_columnas(historial_demanda, COLUMNAS_HISTORIAL, "historial_demanda")

    # --- Paso 1: productos válidos -----------------------------------------
    # Sin productos válidos no hay nada que calcular: se devuelve la salida vacía
    # (con columnas y dtypes) en lugar de dejar que los módulos del motor
    # devuelvan marcos vacíos que después habría que interpretar.
    producto_ids_validos: list = _productos_validos(
        productos, producto_proveedor, historial_demanda
    )
    if not producto_ids_validos:
        return _resultado_vacio()

    # --- Paso 2: CV calculable (clasificación XYZ) --------------------------
    # La clasificación XYZ se hace aquí, sobre los productos del paso 1, porque de
    # ella sale la última exclusión: un producto con demanda media 0 no tiene CV
    # ni clase, y la tabla 'recomendaciones' exige las dos como NOT NULL. Se
    # calcula una sola vez y su resultado se reutiliza en el paso 5.
    historial_filtrado: pd.DataFrame = _filtrar_por_producto(
        historial_demanda, producto_ids_validos
    )
    xyz: pd.DataFrame = clasificar_xyz(
        historial_filtrado,
        umbral_x=parametros["cv_confianza_alta"],
        umbral_y=parametros["cv_confianza_media"],
    ).rename(
        columns={"cv": "cv_demanda"}
    )
    con_cv: set = set(xyz.loc[xyz["cv_demanda"].notna(), "producto_id"])
    producto_ids_validos = [
        producto_id for producto_id in producto_ids_validos if producto_id in con_cv
    ]
    if not producto_ids_validos:
        return _resultado_vacio()

    # Los módulos del motor solo ven los productos que van a la salida: ni los
    # descartados en el paso 1 ni los del paso 2.
    productos_filtrado: pd.DataFrame = _filtrar_por_producto(
        productos, producto_ids_validos
    )
    producto_proveedor_filtrado: pd.DataFrame = _filtrar_por_producto(
        producto_proveedor, producto_ids_validos
    )
    historial_filtrado = _filtrar_por_producto(historial_demanda, producto_ids_validos)
    xyz = xyz[xyz["producto_id"].isin(producto_ids_validos)][
        ["producto_id", "cv_demanda", "clase_xyz"]
    ].reset_index(drop=True)

    # --- Paso 3: proveedor elegido por producto ----------------------------
    elegido: pd.DataFrame = _elegir_proveedor(
        producto_proveedor_filtrado, proveedores, parametros=parametros
    )

    # --- Paso 4: métricas del motor ----------------------------------------
    # ABC: el valor económico es costo_unitario * demanda_total, y la demanda
    # total es la suma histórica de las cantidades demandadas.
    demanda_total: pd.DataFrame = (
        historial_filtrado.groupby("producto_id", sort=True)["cantidad_demandada"]
        .sum()
        .rename("demanda_total")
        .reset_index()
    )
    abc: pd.DataFrame = clasificar_abc(
        productos_filtrado[["producto_id", "costo_unitario"]].merge(
            demanda_total, on="producto_id", how="inner"
        ),
        umbral_clase_a=parametros["abc_clase_a_pct"],
        umbral_clase_b=parametros["abc_clase_b_pct"],
    )[["producto_id", "clase_abc"]]

    # La demanda estimada se alimenta del historial filtrado; la clasificación XYZ
    # se calculó en el paso 2.
    demanda: pd.DataFrame = estimar_demanda(
        historial_filtrado, ventana=int(parametros["demanda_ventana_default"])
    )

    # EOQ / stock de seguridad / punto de reorden: costo del producto + lead time
    # del proveedor elegido + demanda estimada.
    datos_eoq: pd.DataFrame = (
        productos_filtrado[
            [
                "producto_id",
                "costo_unitario",
                "costo_ordenar",
                "costo_mantener_pct_anual",
            ]
        ]
        .merge(
            elegido[["producto_id", "lead_time_dias"]], on="producto_id", how="inner"
        )
        .merge(demanda, on="producto_id", how="inner")
    )
    eoq: pd.DataFrame = calcular_eoq_rop(
        datos_eoq,
        periodos_por_año=periodos_por_año,
        dias_por_periodo=dias_por_periodo,
        margen_seguridad_pct=margen_seguridad_pct,
    )

    # Ahorro por descuento de volumen: se evalúa con el mismo periodos_por_año
    # con el que se anualizó la demanda en el EOQ.
    datos_ahorro: pd.DataFrame = (
        elegido[
            [
                "producto_id",
                "precio_unitario",
                "cantidad_umbral_descuento",
                "descuento_pct",
            ]
        ]
        .merge(eoq[["producto_id", "cantidad_eoq"]], on="producto_id", how="inner")
        .merge(
            productos_filtrado[
                ["producto_id", "costo_unitario", "costo_mantener_pct_anual"]
            ],
            on="producto_id",
            how="inner",
        )
    )
    ahorro: pd.DataFrame = calcular_ahorro(
        datos_ahorro,
        umbral_ahorro_pct=parametros["ahorro_neto_min_pct"],
        periodos_por_año=periodos_por_año,
    )

    # --- Paso 5: combinación (una fila por producto) ------------------------
    # Los merges son 'inner' a propósito: un producto que no sobrevivió a algún
    # módulo no debe aparecer en la salida con métricas incompletas.
    resultado: pd.DataFrame = (
        elegido.merge(abc, on="producto_id", how="inner")
        .merge(xyz, on="producto_id", how="inner")
        .merge(demanda, on="producto_id", how="inner")
        .merge(eoq, on="producto_id", how="inner")
        .merge(ahorro, on="producto_id", how="inner")
        .merge(
            productos_filtrado[
                [
                    "producto_id",
                    "nombre",
                    "categoria",
                    "stock_actual",
                    "costo_unitario",
                    "costo_ordenar",
                    "costo_mantener_pct_anual",
                ]
            ],
            on="producto_id",
            how="inner",
        )
        .rename(
            columns={
                "cantidad_pedido": "cantidad_recomendada",
                "ahorro_neto": "ahorro_neto_estimado",
                "estado": "estado_ahorro",
            }
        )
    )

    # Dato auxiliar para el evaluador: costo del pedido sugerido.
    resultado["costo_total_pedido"] = (
        resultado["cantidad_recomendada"].astype("float64")
        * resultado["precio_unitario"].astype("float64")
    )

    # --- Paso 6: urgencia (marca, no filtra) --------------------------------
    # Se calcula vectorizado con el mismo estilo que los módulos del motor. Los
    # cortes son inclusivos y excluyentes: Crítico alcanza el stock de seguridad
    # (<=), Atención alcanza el punto de reorden (<=) y Sin riesgo queda por
    # encima de él.
    stock_actual: np.ndarray = resultado["stock_actual"].to_numpy(dtype="float64")
    stock_seguridad: np.ndarray = resultado["stock_seguridad"].to_numpy(dtype="float64")
    punto_reorden: np.ndarray = resultado["punto_reorden"].to_numpy(dtype="float64")
    resultado["urgencia"] = np.select(
        [
            stock_actual <= stock_seguridad,
            stock_actual <= punto_reorden,
        ],
        [URGENCIA_CRITICO, URGENCIA_ATENCION],
        default=URGENCIA_SIN_RIESGO,
    )

    # Un nulo en una columna obligatoria es un error, no una fila a descartar.
    _verificar_sin_nulos(resultado)

    # --- Paso 7: orden ------------------------------------------------------
    # La columna se vuelve categórica ordenada para que el orden sea el de
    # negocio (Crítico > Atención > Sin riesgo) y no el alfabético.
    #
    # OJO: las categorías quedan en el orden de prioridad de ORDEN_URGENCIA, así
    # que 'Crítico' es la categoría MENOR y el orden pedido ("Crítico primero,
    # luego Atención, luego Sin riesgo") se obtiene con ascending=True sobre la
    # categórica. Con ascending=False el resultado sería el inverso (Sin riesgo,
    # Atención, Crítico), que es el efecto de tratar la prioridad como si fuera
    # un score numérico.
    resultado = resultado[list(COLUMNAS_SALIDA)]
    resultado["urgencia"] = pd.Categorical(
        resultado["urgencia"], categories=ORDEN_URGENCIA, ordered=True
    )

    return resultado.sort_values(
        by=["urgencia", "ahorro_neto_estimado", "producto_id"],
        ascending=[True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def generar_recomendaciones(supabase_client) -> pd.DataFrame:
    """
    Lee Supabase, normaliza los nombres de columna y calcula las recomendaciones.

    Lee completas las tablas ``productos``, ``proveedores``, ``producto_proveedor``
    e ``historial_demanda``, convierte cada resultado a DataFrame y renombra las
    columnas que el motor no espera con su nombre de tabla:

    * ``productos``: ``id`` -> ``producto_id``.
    * ``proveedores``: ``id`` -> ``proveedor_id`` y
      ``nombre`` -> ``proveedor_nombre``.
    * ``producto_proveedor`` e ``historial_demanda``: no se tocan (ya usan
      ``producto_id`` y ``proveedor_id``, y el renombre de ``proveedores`` no los
      afecta).

    Después carga los parámetros de configuración con
    :func:`src.config.cargar_parametros` (tabla ``parametros_configuracion``) y
    delega todo el cálculo en :func:`calcular_recomendaciones`, pasándoselos ya
    resueltos para que la función pura no toque la base de datos. Esta función
    **no** permite ajustar los tres parámetros de :mod:`src.motor.eoq_rop`
    (``periodos_por_año``, ``dias_por_periodo`` y ``margen_seguridad_pct``):
    siguen tomando sus defaults.

    Args:
        supabase_client: cliente de Supabase ya configurado. Alcanza con la
            ``anon key`` porque esta función solo lee.

    Returns:
        El DataFrame que devuelve :func:`calcular_recomendaciones`.

    Notas:
        - Solo hace E/S: no contiene lógica de negocio ni escribe en Supabase.
        - El orden de las filas que devuelve la API no está garantizado, así que
          el desempate de proveedores con el mismo score y el mismo precio puede
          variar entre ejecuciones (ver :func:`calcular_recomendaciones`).
        - Los umbrales del motor no se eligen aquí: salen de la tabla
          ``parametros_configuracion`` y los carga
          :func:`src.config.cargar_parametros` (ver
          :func:`calcular_recomendaciones`). Si a esa tabla le falta un
          parámetro, :func:`src.config.cargar_parametros` lanza ``ValueError``.
        - Esta función no permite ajustar los tres parámetros de
          :mod:`src.motor.eoq_rop` (``periodos_por_año``, ``dias_por_periodo``,
          ``margen_seguridad_pct``): un llamador que los necesite debe leer los
          datos y los parámetros por su cuenta y llamar a
          :func:`calcular_recomendaciones` directamente.

    Raises:
        ValueError: si alguna de las cuatro tablas de datos viene vacía (sin
            filas no hay columnas que validar y no se puede calcular nada).
        ValueError: si a la tabla ``parametros_configuracion`` le falta algún
            parámetro esperado (incluida la tabla vacía); lo lanza
            :func:`src.config.verificar_parametros` a través de
            :func:`src.config.cargar_parametros`.
        Exception: cualquier error de red o de la API de Supabase (credenciales
            inválidas, tabla inexistente, timeout) se propaga tal cual. Un fallo
            de Supabase al leer los parámetros se propaga igual que el de las
            cuatro tablas de datos.
    """
    productos: pd.DataFrame = _leer_tabla(supabase_client, "productos").rename(
        columns={"id": "producto_id"}
    )
    proveedores: pd.DataFrame = _leer_tabla(supabase_client, "proveedores").rename(
        columns={"id": "proveedor_id", "nombre": "proveedor_nombre"}
    )
    producto_proveedor: pd.DataFrame = _leer_tabla(
        supabase_client, "producto_proveedor"
    )
    historial_demanda: pd.DataFrame = _leer_tabla(supabase_client, "historial_demanda")

    # Los umbrales del motor salen de la tabla de configuración; si a Supabase le
    # falta algún parámetro, cargar_parametros lanza ValueError y la excepción se
    # propaga tal cual (mismo contrato que las lecturas de arriba). Se leen
    # después de los datos para no hacer una petición extra cuando las tablas de
    # datos están vacías o fallan.
    parametros: dict[str, float] = cargar_parametros(supabase_client)

    return calcular_recomendaciones(
        productos,
        proveedores,
        producto_proveedor,
        historial_demanda,
        parametros=parametros,
    )


def guardar_recomendaciones(
    supabase_client,
    recomendaciones: pd.DataFrame,
) -> pd.DataFrame:
    """
    Escribe las recomendaciones en la tabla ``recomendaciones`` de Supabase.

    Filtra las columnas de :data:`COLUMNAS_RECOMENDACIONES` (las que van a la
    tabla; ``id``, ``fecha_generacion`` y ``estado`` los pone Supabase por default
    con ``now()`` y ``'pendiente'``), las convierte en una lista de diccionarios y
    las inserta con ``insert``. Las filas insertadas, con sus ``id`` ya generados,
    se devuelven como DataFrame.

    Args:
        supabase_client: cliente de Supabase configurado con la
            **service_role key**. La tabla tiene RLS habilitado con políticas de
            solo lectura, así que con la ``anon key`` el ``insert`` falla.
        recomendaciones: DataFrame tal como lo devuelve
            :func:`calcular_recomendaciones` (o cualquier DataFrame con las
            columnas de :data:`COLUMNAS_RECOMENDACIONES`).

    Returns:
        DataFrame con las filas que devolvió la API tras el ``insert``, es decir
        las recomendaciones ya persistidas con las columnas de la tabla
        ``recomendaciones``: ``id`` (el uuid generado por Supabase),
        ``producto_id``, ``proveedor_id``, ``fecha_generacion``,
        ``demanda_estimada``, ``cv_demanda``, ``punto_reorden``,
        ``stock_seguridad``, ``cantidad_eoq``, ``cantidad_recomendada``,
        ``clase_abc``, ``clase_xyz``, ``lead_time_dias``, ``precio_unitario``,
        ``ahorro_neto_estimado`` y ``estado``. Un DataFrame sin filas devuelve un
        DataFrame vacío: no se hace ninguna petición y no hay nada que devolver.

    Notas:
        - Solo hace E/S: no calcula nada ni modifica ``recomendaciones``.
        - No escribe en ``evaluaciones_criterios``: esa es responsabilidad del
          evaluador de la rúbrica.
        - El ``id`` que devuelve esta función es el ``recomendacion_id`` que
          necesita el evaluador de la rúbrica. Como el ``insert`` solo devuelve
          las columnas de la tabla, para armar su entrada hay que cruzar estos
          ``id`` con el DataFrame original (por ``producto_id``): las columnas
          ``stock_actual``, ``costo_total_pedido`` y ``score_proveedor``, entre
          otras, no se guardan en ``recomendaciones``.
        - Los escalares de numpy (``np.int64``, ``np.float64``, ...) se convierten
          a tipos nativos antes de insertar, porque el cliente de Supabase
          serializa el cuerpo con el módulo ``json`` estándar, que no los sabe
          serializar.
        - Si la API no devolviera las filas insertadas (``data`` nulo o vacío) se
          devuelve un DataFrame vacío en lugar de fallar: el ``insert`` ya se
          hizo.

    Raises:
        ValueError: si al DataFrame le falta alguna columna de
            :data:`COLUMNAS_RECOMENDACIONES`.
        Exception: cualquier error de la API de Supabase (RLS, clave foránea
            inexistente, columna nula en un ``not null``, timeout) se propaga tal
            cual.
    """
    faltantes: list[str] = [
        columna
        for columna in COLUMNAS_RECOMENDACIONES
        if columna not in recomendaciones.columns
    ]
    if faltantes:
        raise ValueError(
            "guardar_recomendaciones: a las recomendaciones les faltan las "
            "columnas que se escriben en la tabla 'recomendaciones'; faltan: "
            f"{', '.join(faltantes)}."
        )

    seleccion: pd.DataFrame = recomendaciones[list(COLUMNAS_RECOMENDACIONES)]
    if seleccion.empty:
        return pd.DataFrame()

    registros: list[dict[str, object]] = [
        {columna: _escalar_nativo(valor) for columna, valor in fila.items()}
        for fila in seleccion.to_dict(orient="records")
    ]

    respuesta = supabase_client.table("recomendaciones").insert(registros).execute()

    # La API devuelve las filas insertadas en 'data', ya con el id (uuid) y los
    # valores por defecto que puso Supabase. Si no viniera nada, se devuelve un
    # DataFrame vacío en lugar de fallar: el insert ya se realizó.
    return pd.DataFrame(respuesta.data if respuesta.data else [])


def _productos_validos(
    productos: pd.DataFrame,
    producto_proveedor: pd.DataFrame,
    historial_demanda: pd.DataFrame,
) -> list:
    """IDs de los productos que cumplen los criterios mínimos (paso 1).

    Un producto es válido si aparece en ``productos`` (es el universo de la
    salida), tiene al menos :data:`~src.motor.xyz.MIN_PERIODOS` filas de historial
    y tiene al menos una fila en ``producto_proveedor``.

    Args:
        productos: catálogo de productos, ya validado por columnas.
        producto_proveedor: relación producto-proveedor, ya validada.
        historial_demanda: historial en formato largo, ya validado.

    Returns:
        Lista de ``producto_id`` en el orden de aparición en ``productos``, sin
        repetir. Se cuentan **filas** de historial, no periodos distintos, para
        que el criterio coincida exactamente con el que aplica
        :func:`src.motor.xyz.clasificar_xyz` (el schema garantiza una fila por
        producto y periodo).

    Notas:
        Esta lista es la de candidatos del paso 1: :func:`calcular_recomendaciones`
        todavía descarta, en su paso 2, a los productos cuyo coeficiente de
        variación no es calculable.
    """
    filas_por_producto: pd.Series = historial_demanda.groupby("producto_id").size()
    con_historial_suficiente: pd.Index = filas_por_producto[
        filas_por_producto >= MIN_PERIODOS
    ].index
    con_proveedor: pd.Index = producto_proveedor["producto_id"].drop_duplicates()

    mascara: pd.Series = productos["producto_id"].isin(con_historial_suficiente) & (
        productos["producto_id"].isin(con_proveedor)
    )
    return list(pd.unique(productos.loc[mascara, "producto_id"]))


def _filtrar_por_producto(datos: pd.DataFrame, producto_ids: list) -> pd.DataFrame:
    """Copia de ``datos`` con las filas de los productos válidos.

    Args:
        datos: DataFrame con columna ``producto_id``.
        producto_ids: IDs válidos que deben conservarse.

    Returns:
        DataFrame nuevo (la selección booleana no toca la entrada) con solo esas
        filas.
    """
    return datos[datos["producto_id"].isin(producto_ids)]


def _proveedores_con_score(
    proveedores: pd.DataFrame,
    parametros: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Cataloga a los proveedores con su score (paso 3).

    Args:
        proveedores: catálogo de proveedores, ya validado por columnas.
        parametros: parámetros de configuración ya resueltos por
            :func:`calcular_recomendaciones` (None = usar
            :data:`src.config.PARAMETROS_DEFAULT`). De aquí salen los dos cortes
            del score que recibe
            :func:`src.motor.proveedor.calcular_score_proveedor`.

    Returns:
        DataFrame con ``proveedor_id``, ``proveedor_nombre``,
        ``cumplimiento_entrega_pct``, ``tasa_defectos_pct`` y ``score_proveedor``
        (el ``score`` de :func:`src.motor.proveedor.calcular_score_proveedor`).
        Se eliminan las filas repetidas por ``proveedor_id`` para que el merge
        posterior sea 1:1: el schema declara ``id`` como clave primaria, así que
        la deduplicación no debería activarse nunca, pero si llegara un catálogo
        con IDs repetidos el merge no multiplicaría candidatos en silencio.

    Notas:
        El ``estado`` del proveedor (Confiable / Aceptable con reservas /
        Riesgoso) no viaja a la salida: :data:`COLUMNAS_PROVEEDOR_ELEGIDO` no lo
        incluye. Los cortes se propagan igualmente porque son parte de la
        parametrización del motor y el llamador espera que el módulo se evalúe
        con los valores de ``parametros_configuracion``; lo que decide al
        proveedor elegido es el ``score``, que no depende de ellos.
    """
    umbrales: dict[str, float] = (
        PARAMETROS_DEFAULT if parametros is None else parametros
    )
    puntajes: pd.DataFrame = (
        calcular_score_proveedor(
            proveedores,
            umbral_confiable=umbrales["score_proveedor_confiable"],
            umbral_riesgoso=umbrales["score_proveedor_riesgoso"],
        )
        .rename(columns={"score": "score_proveedor"})[
            ["proveedor_id", "score_proveedor"]
        ]
        .drop_duplicates(subset="proveedor_id", keep="first")
    )
    catalogo: pd.DataFrame = proveedores[
        [
            "proveedor_id",
            "proveedor_nombre",
            "cumplimiento_entrega_pct",
            "tasa_defectos_pct",
        ]
    ].drop_duplicates(subset="proveedor_id", keep="first")

    return catalogo.merge(puntajes, on="proveedor_id", how="inner")


def _elegir_proveedor(
    producto_proveedor: pd.DataFrame,
    proveedores: pd.DataFrame,
    parametros: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Elige un proveedor por producto: mayor score y, en empate, menor precio.

    Args:
        producto_proveedor: relación producto-proveedor de los productos válidos.
        proveedores: catálogo completo de proveedores.
        parametros: parámetros de configuración ya resueltos (None = usar
            :data:`src.config.PARAMETROS_DEFAULT`), reenviados tal cual a
            :func:`_proveedores_con_score` para que los cortes del score salgan
            de la configuración.

    Returns:
        DataFrame con una fila por producto y las columnas de
        :data:`COLUMNAS_PROVEEDOR_ELEGIDO`. Las relaciones cuyo ``proveedor_id``
        no está en ``proveedores`` se descartan (imposible con la clave foránea
        del schema); si un producto se queda sin ninguna, no aparece aquí y los
        merges ``inner`` del paso 4 lo dejan fuera de la salida.
    """
    candidatos: pd.DataFrame = producto_proveedor.merge(
        _proveedores_con_score(proveedores, parametros), on="proveedor_id", how="inner"
    )

    # Orden por producto y, dentro de cada producto, score descendente y precio
    # ascendente: el primer registro de cada grupo es el proveedor elegido.
    # 'mergesort' es estable, así que un empate doble (mismo score y mismo precio)
    # se resuelve por el orden de aparición en producto_proveedor.
    elegido: pd.DataFrame = candidatos.sort_values(
        by=["producto_id", "score_proveedor", "precio_unitario"],
        ascending=[True, False, True],
        kind="mergesort",
    ).drop_duplicates(subset="producto_id", keep="first")

    return elegido[list(COLUMNAS_PROVEEDOR_ELEGIDO)].reset_index(drop=True)


def _verificar_sin_nulos(recomendaciones: pd.DataFrame) -> None:
    """Verifica que las columnas obligatorias de la salida no tengan nulos.

    Args:
        recomendaciones: DataFrame combinado de :func:`calcular_recomendaciones`,
            antes de reordenar columnas.

    Raises:
        ValueError: si alguna columna de :data:`COLUMNAS_NO_NULAS` tiene nulos.
            El mensaje indica la columna y los ``producto_id`` afectados, para
            poder ir directo al dato que el motor no pudo calcular.
    """
    con_nulos: dict[str, list[str]] = {}
    for columna in COLUMNAS_NO_NULAS:
        nulos: pd.Series = recomendaciones[columna].isna()
        if bool(nulos.any()):
            con_nulos[columna] = sorted(
                {str(valor) for valor in recomendaciones.loc[nulos, "producto_id"]}
            )

    if con_nulos:
        detalle: str = "; ".join(
            f"{columna} -> {', '.join(ids)}" for columna, ids in con_nulos.items()
        )
        raise ValueError(
            "calcular_recomendaciones: hay valores nulos en columnas que no "
            f"admiten nulos ({', '.join(COLUMNAS_NO_NULAS)}): {detalle}."
        )


def _verificar_columnas(
    datos: pd.DataFrame,
    requeridas: tuple[str, ...],
    nombre: str,
) -> None:
    """Valida que un DataFrame de entrada traiga las columnas requeridas.

    Args:
        datos: DataFrame de entrada tal como llegó del llamador.
        requeridas: columnas que el módulo necesita de ese DataFrame.
        nombre: nombre del parámetro en la firma, para que el mensaje señale al
            llamador cuál de los cuatro DataFrames corregir.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna for columna in requeridas if columna not in datos.columns
    ]
    if faltantes:
        raise ValueError(
            f"calcular_recomendaciones: al DataFrame '{nombre}' le faltan "
            f"columnas requeridas: {', '.join(faltantes)}. Se esperaban: "
            f"{', '.join(requeridas)}."
        )


def _leer_tabla(supabase_client, tabla: str) -> pd.DataFrame:
    """Lee una tabla completa de Supabase y la devuelve como DataFrame.

    Args:
        supabase_client: cliente de Supabase ya configurado.
        tabla: nombre de la tabla a leer.

    Returns:
        DataFrame con todas las filas y columnas de la tabla.

    Raises:
        ValueError: si la tabla no devuelve filas. Una lista vacía no tiene
            columnas, así que el motor no podría validarlas y el error real
            quedaría escondido detrás de un "faltan columnas"; se falla aquí con
            el nombre de la tabla.
        Exception: cualquier error de red o de la API se propaga tal cual.
    """
    respuesta = supabase_client.table(tabla).select("*").execute()
    if not respuesta.data:
        raise ValueError(
            f"generar_recomendaciones: la tabla '{tabla}' no devolvió filas; "
            "sin datos no se pueden generar recomendaciones."
        )
    return pd.DataFrame(respuesta.data)


def _escalar_nativo(valor: object) -> object:
    """Convierte un escalar de numpy al tipo nativo equivalente.

    Args:
        valor: valor de una celda tal como lo devuelve ``to_dict``.

    Returns:
        El mismo valor como ``int``, ``float`` o ``bool`` de Python si era un
        escalar de numpy; en cualquier otro caso, el valor sin tocar.

    Notas:
        El cliente de Supabase serializa el cuerpo de la petición con el módulo
        ``json`` estándar, que no sabe serializar los escalares de numpy
        (``np.int64`` no es subclase de ``int``). Un DataFrame construido desde
        JSON, como el que devuelve :func:`generar_recomendaciones`, trae columnas
        como ``lead_time_dias`` en ``int64``, así que la conversión evita un error
        de serialización al escribir. El número no cambia: solo su tipo Python.
    """
    if isinstance(valor, np.bool_):
        return bool(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    return valor


def _resultado_vacio() -> pd.DataFrame:
    """Devuelve la salida vacía, con las columnas y dtypes de la salida real.

    Returns:
        DataFrame sin filas con todas las columnas de :data:`COLUMNAS_SALIDA`, las
        de texto como ``object``, las numéricas como ``float64`` y ``urgencia``
        como categórica ordenada con las categorías de :data:`ORDEN_URGENCIA`
        (para que la salida vacía tenga el mismo contrato que la no vacía).
    """
    return pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "proveedor_id": pd.Series(dtype=object),
            "proveedor_nombre": pd.Series(dtype=object),
            "nombre": pd.Series(dtype=object),
            "categoria": pd.Series(dtype=object),
            "clase_abc": pd.Series(dtype=object),
            "clase_xyz": pd.Series(dtype=object),
            "cv_demanda": pd.Series(dtype="float64"),
            "demanda_estimada": pd.Series(dtype="float64"),
            "cantidad_eoq": pd.Series(dtype="float64"),
            "stock_seguridad": pd.Series(dtype="float64"),
            "punto_reorden": pd.Series(dtype="float64"),
            "lead_time_dias": pd.Series(dtype="float64"),
            "precio_unitario": pd.Series(dtype="float64"),
            "score_proveedor": pd.Series(dtype="float64"),
            "cantidad_recomendada": pd.Series(dtype="float64"),
            "ahorro_neto_estimado": pd.Series(dtype="float64"),
            "estado_ahorro": pd.Series(dtype=object),
            "stock_actual": pd.Series(dtype="float64"),
            "costo_unitario": pd.Series(dtype="float64"),
            "costo_ordenar": pd.Series(dtype="float64"),
            "costo_mantener_pct_anual": pd.Series(dtype="float64"),
            "ahorro_bruto": pd.Series(dtype="float64"),
            "costo_extra_mantener": pd.Series(dtype="float64"),
            "costo_total_pedido": pd.Series(dtype="float64"),
            "urgencia": pd.Series(
                pd.Categorical([], categories=ORDEN_URGENCIA, ordered=True)
            ),
            "cantidad_umbral_descuento": pd.Series(dtype="float64"),
            "descuento_pct": pd.Series(dtype="float64"),
        }
    )

