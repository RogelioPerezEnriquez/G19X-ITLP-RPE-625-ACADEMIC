"""Aplicación de la rúbrica de 6 criterios a las recomendaciones de compra.

Pieza final del pipeline del MVP: toma las recomendaciones que **ya están
persistidas** en la tabla ``recomendaciones``, les aplica los seis criterios de
evaluación de ``MVP.md`` §10 y deja el resultado listo para escribir en la tabla
``evaluaciones_criterios``. Expone tres funciones con responsabilidades
separadas:

* :func:`evaluar_recomendaciones` -- función **pura**: recibe un DataFrame y
  devuelve un DataFrame. Orquesta la rúbrica, no accede a red, base de datos ni
  archivos, no imprime ni registra nada y no modifica la entrada. Es la parte
  testeable.
* :func:`guardar_evaluaciones` -- escribe las evaluaciones en la tabla
  ``evaluaciones_criterios``. Solo hace E/S: no calcula nada.
* :func:`evaluar_y_guardar` -- conveniencia para el llamador: aplica la rúbrica
  y guarda el resultado sin tener que llamar a las dos funciones por separado.

Contrato de ``recomendacion_id``
--------------------------------
La tabla ``recomendaciones`` tiene ``id`` (uuid) y lo genera Supabase al
insertar; ``evaluaciones_criterios.recomendacion_id`` es una clave foránea a esa
columna. Por eso el DataFrame que recibe :func:`evaluar_recomendaciones` **debe**
traer la columna ``recomendacion_id`` con los UUID de recomendaciones ya
persistidas.

``evaluar_recomendaciones`` **no genera ni modifica identificadores**: no
inventa UUID "provisionales", no convierte ``None`` en un UUID y no consulta la
base para resolverlos. Los asigna el llamador (por ejemplo, al releer la tabla
después de escribirla) y este módulo se limita a copiarlos en la salida. Si
algún ``recomendacion_id`` es nulo o inválido, el ``insert`` de
:func:`guardar_evaluaciones` fallará por clave foránea: es responsabilidad del
llamador, no del evaluador.

Los 6 criterios (``MVP.md`` §10)
--------------------------------
1. ``riesgo_quiebre_stock``: Crítico / Atención / Sin riesgo.
   ``valor_numerico`` = ``stock_actual``.
2. ``eficiencia_cantidad_eoq``: Pedido muy pequeño / Óptima / Pedido excesivo.
   ``valor_numerico`` = ``cantidad_recomendada / cantidad_eoq``.
3. ``confianza_demanda``: Alta confianza / Confianza moderada / Baja confianza
   (revisión manual). ``valor_numerico`` = ``cv_demanda``.
4. ``importancia_producto``: Alta / Media / Baja (tabla ABC x XYZ).
   ``valor_numerico`` = ``None``.
5. ``confiabilidad_proveedor``: Confiable / Aceptable con reservas / Riesgoso.
   ``valor_numerico`` = ``score_proveedor``.
6. ``oportunidad_ahorro``: Ahorro detectado / Sin oportunidad adicional.
   ``valor_numerico`` = ``ahorro_neto_estimado``.

El orden de los criterios en :data:`ORDEN_CRITERIOS` coincide con el orden del
``check`` de la tabla ``evaluaciones_criterios`` en ``db/schema.sql``.

Tolerancias en las fronteras
----------------------------
Los cortes inclusivos se evalúan con la tolerancia sumada (o restada, según el
lado inclusivo) al umbral, igual que :data:`~src.motor.abc.TOLERANCIA_PCT`,
:data:`~src.motor.xyz.TOLERANCIA_CV`,
:data:`~src.motor.proveedor.TOLERANCIA_SCORE` y
:data:`~src.motor.ahorro.TOLERANCIA_AHORRO`:

* :data:`TOLERANCIA_RATIO` (1e-9): ``ratio < 0.90 - tol`` es "Pedido muy
  pequeño" y ``ratio > 1.10 + tol`` es "Pedido excesivo"; el resto es "Óptima".
* :data:`TOLERANCIA_CV` (1e-9): ``cv <= 0.5 + tol`` es "Alta confianza" y
  ``cv <= 1.0 + tol`` es "Confianza moderada".
* :data:`TOLERANCIA_SCORE` (1e-9): ``score >= 80 - tol`` es "Confiable" y
  ``score < 60 - tol`` es "Riesgoso".
* :data:`TOLERANCIA_AHORRO` (1e-9): ``ahorro_neto >= 0.03 *
  costo_total_pedido - tol`` es "Ahorro detectado".

El criterio 1 (riesgo de quiebre) compara ``stock_actual`` con
``stock_seguridad`` y ``punto_reorden`` **sin** tolerancia: el alcance de esta
sesión define tolerancias para los cuatro criterios anteriores, así que sus
cortes se evalúan tal cual los enuncia ``MVP.md`` §10.

Estrategia de construcción de la salida
---------------------------------------
La salida tiene una fila por ``(recomendacion_id, criterio)``, es decir 6 filas
por recomendación. Se construye con **``pd.concat`` de seis sub-DataFrames** (uno
por criterio), en el orden de :data:`ORDEN_CRITERIOS`, en lugar de un merge
largo: cada criterio calcula su estado y su valor sobre los mismos arrays de
numpy (``np.select``) y solo hay que apilarlos, sin pasar por una tabla
intermedia de llaves, sin productos cartesianos accidentales y sin alinear nada
(los seis sub-DataFrames comparten el mismo ``recomendacion_id``, fila a fila).

Contrato de la salida
---------------------
DataFrame con las columnas de :data:`COLUMNAS_SALIDA`, en este orden:
``recomendacion_id``, ``criterio``, ``estado`` y ``valor_numerico``.

* ``criterio`` es un ``pd.Categorical`` ordenado con las categorías de
  :data:`ORDEN_CRITERIOS`, y la salida está ordenada por
  ``(recomendacion_id, criterio)`` con ese orden **lógico** (no alfabético). El
  índice es un ``RangeIndex`` desde 0.
* ``valor_numerico`` es ``float64`` donde se puede calcular (``stock_actual``,
  ``ratio``, ``cv_demanda``, ``score_proveedor``, ``ahorro_neto_estimado``).
* ``valor_numerico`` es ``None`` para ``importancia_producto``: es el único
  criterio categórico puro, sin valor numérico asociado. En la base de datos la
  columna es ``numeric`` nullable, así que ``None`` se escribe como ``NULL``.
  Como la columna de la salida mezcla ``float`` con ``None``, su ``dtype`` es
  ``object``; cada celda numérica sigue siendo un ``float`` de verdad.

Casos borde
-----------
* DataFrame sin filas pero con las columnas requeridas: se devuelve la salida
  vacía con las cuatro columnas, el ``dtype`` de cada una y ``criterio`` como
  categórica ordenada, para que el contrato no cambie.
* Combinación ``clase_abc`` x ``clase_xyz`` fuera de la tabla del criterio 4
  (fuera de A/B/C x X/Y/Z): ``ValueError``. El motor solo produce esas nueve
  combinaciones y ``estado`` es ``not null`` en el schema, así que un dato fuera
  de contrato se reporta en lugar de escribir un ``NULL`` en silencio.
* ``cantidad_eoq = 0``: el motor garantiza ``cantidad_eoq > 0`` (``H > 0`` en
  :mod:`src.motor.eoq_rop`) y este módulo no valida rangos, igual que el resto
  del motor. Con ``cantidad_eoq = 0`` el ratio sería ``inf`` (``nan`` si las dos
  cantidades fueran 0) y el estado caería en "Pedido excesivo" ("Óptima" con
  ``nan``): es un dato fuera de contrato, no un caso soportado.

Contrato de errores
-------------------
``ValueError`` si falta alguna columna de :data:`COLUMNAS_REQUERIDAS` (con o sin
filas) o si aparece una combinación ABC/XYZ fuera de la tabla del criterio 4. Los
errores de la API de Supabase se propagan tal cual desde
:func:`guardar_evaluaciones`.

"""

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - solo para las anotaciones de tipo
    # El cliente se importa solo para el chequeo de tipos: así el módulo (y los
    # tests de su función pura) no dependen del paquete 'supabase' en tiempo de
    # ejecución.
    from supabase import Client

__all__ = [
    "evaluar_recomendaciones",
    "guardar_evaluaciones",
    "evaluar_y_guardar",
]

# ---------------------------------------------------------------- los criterios

CRITERIO_RIESGO: str = "riesgo_quiebre_stock"
CRITERIO_EFICIENCIA: str = "eficiencia_cantidad_eoq"
CRITERIO_CONFIANZA: str = "confianza_demanda"
CRITERIO_IMPORTANCIA: str = "importancia_producto"
CRITERIO_CONFIABILIDAD: str = "confiabilidad_proveedor"
CRITERIO_AHORRO: str = "oportunidad_ahorro"

# Orden lógico de la rúbrica. Se usa como categorías de la columna 'criterio'
# para que el orden de la salida sea el de los criterios (1 a 6) y no el
# alfabético. Coincide con el orden del 'check' de evaluaciones_criterios.
ORDEN_CRITERIOS: list[str] = [
    CRITERIO_RIESGO,
    CRITERIO_EFICIENCIA,
    CRITERIO_CONFIANZA,
    CRITERIO_IMPORTANCIA,
    CRITERIO_CONFIABILIDAD,
    CRITERIO_AHORRO,
]


# ------------------------------------------------------------------ umbrales

# Umbrales de corte de la rúbrica. Fuente única de verdad: cuando el MVP
# incorpore la tabla de configuración (fase 4), estos serán sus valores por
# defecto.
# Criterio 2: cantidad recomendada / cantidad EOQ.
RATIO_MIN: float = 0.90
RATIO_MAX: float = 1.10
# Criterio 3: coeficiente de variación de la demanda (los mismos cortes que
# UMBRAL_X y UMBRAL_Y de src.motor.xyz).
CV_ALTA: float = 0.5
CV_MODERADA: float = 1.0
# Criterio 5: score de confiabilidad del proveedor (los mismos cortes que
# UMBRAL_CONFIABLE y UMBRAL_RIESGOSO de src.motor.proveedor).
SCORE_CONFIABLE: float = 80.0
SCORE_RIESGOSO: float = 60.0
# Criterio 6: 3 % del costo total del pedido, expresado como fracción porque se
# multiplica directamente por el costo (3 % = 0.03). Ojo con la diferencia de
# unidad: src.motor.ahorro define UMBRAL_AHORRO_PCT_DEFAULT = 3.0 porque allí se
# divide entre 100.
AHORRO_PCT: float = 0.03

# Tolerancias al comparar contra los umbrales. Absorben el ruido de punto
# flotante en los cortes exactos, con el mismo criterio (y el mismo valor) que
# TOLERANCIA_PCT (abc.py), TOLERANCIA_CV (xyz.py), TOLERANCIA_SCORE
# (proveedor.py) y TOLERANCIA_AHORRO (ahorro.py).
TOLERANCIA_RATIO: float = 1e-9
TOLERANCIA_CV: float = 1e-9
TOLERANCIA_SCORE: float = 1e-9
TOLERANCIA_AHORRO: float = 1e-9


# ------------------------------------------------------- etiquetas de estado

# Criterio 1: riesgo de quiebre de stock.
ESTADO_CRITICO: str = "Crítico"
ESTADO_ATENCION: str = "Atención"
ESTADO_SIN_RIESGO: str = "Sin riesgo"

# Criterio 2: eficiencia de la cantidad pedida contra el EOQ.
ESTADO_PEDIDO_PEQUENO: str = "Pedido muy pequeño"
ESTADO_OPTIMA: str = "Óptima"
ESTADO_PEDIDO_EXCESIVO: str = "Pedido excesivo"

# Criterio 3: confianza en la demanda estimada.
ESTADO_ALTA_CONFIANZA: str = "Alta confianza"
ESTADO_CONFIANZA_MODERADA: str = "Confianza moderada"
ESTADO_BAJA_CONFIANZA: str = "Baja confianza (revisión manual)"

# Criterio 4: importancia del producto (valores de la tabla de doble entrada).
IMPORTANCIA_ALTA: str = "Alta"
IMPORTANCIA_MEDIA: str = "Media"
IMPORTANCIA_BAJA: str = "Baja"

# Tabla de doble entrada del criterio 4, tal como la enuncia MVP.md §10. La llave
# es (clase_abc, clase_xyz). Las nueve combinaciones están definidas: cualquier
# otra llave es un dato fuera de contrato y se reporta con ValueError.
IMPORTANCIA_POR_CLASE: dict[tuple[str, str], str] = {
    ("A", "X"): IMPORTANCIA_ALTA,
    ("A", "Y"): IMPORTANCIA_ALTA,
    ("A", "Z"): IMPORTANCIA_MEDIA,
    ("B", "X"): IMPORTANCIA_ALTA,
    ("B", "Y"): IMPORTANCIA_MEDIA,
    ("B", "Z"): IMPORTANCIA_MEDIA,
    ("C", "X"): IMPORTANCIA_MEDIA,
    ("C", "Y"): IMPORTANCIA_BAJA,
    ("C", "Z"): IMPORTANCIA_BAJA,
}

# Criterio 5: confiabilidad del proveedor.
ESTADO_CONFIABLE: str = "Confiable"
ESTADO_ACEPTABLE_CON_RESERVAS: str = "Aceptable con reservas"
ESTADO_RIESGOSO: str = "Riesgoso"

# Criterio 6: oportunidad de ahorro por volumen.
ESTADO_AHORRO_DETECTADO: str = "Ahorro detectado"
ESTADO_SIN_OPORTUNIDAD: str = "Sin oportunidad adicional"


# ------------------------------------------------------------------ columnas

# Columnas que debe traer el DataFrame de entrada de
# :func:`evaluar_recomendaciones`. Son las que produce el recomendador
# (:data:`src.recomendador.COLUMNAS_SALIDA`) más ``recomendacion_id``, que el
# llamador añade después de persistir las recomendaciones.
COLUMNAS_REQUERIDAS: tuple[str, ...] = (
    "recomendacion_id",
    "producto_id",
    "stock_actual",
    "stock_seguridad",
    "punto_reorden",
    "cantidad_recomendada",
    "cantidad_eoq",
    "cv_demanda",
    "clase_abc",
    "clase_xyz",
    "score_proveedor",
    "ahorro_neto_estimado",
    "costo_total_pedido",
)

# Columnas de la salida, en orden. Son también las que se escriben en la tabla
# 'evaluaciones_criterios': 'id' y 'creado_en' los pone Supabase con sus valores
# por defecto (gen_random_uuid() y now()).
COLUMNAS_SALIDA: tuple[str, ...] = (
    "recomendacion_id",
    "criterio",
    "estado",
    "valor_numerico",
)

# Tabla en la que escribe :func:`guardar_evaluaciones`.
TABLA_EVALUACIONES: str = "evaluaciones_criterios"



def evaluar_recomendaciones(recomendaciones: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica la rúbrica de 6 criterios a cada recomendación de compra.

    Args:
        recomendaciones: DataFrame con una fila por recomendación, con las
            columnas de :data:`COLUMNAS_REQUERIDAS`:
            ``recomendacion_id`` (UUID de la recomendación ya persistida),
            ``producto_id``, ``stock_actual``, ``stock_seguridad``,
            ``punto_reorden``, ``cantidad_recomendada``, ``cantidad_eoq``,
            ``cv_demanda``, ``clase_abc``, ``clase_xyz``, ``score_proveedor``,
            ``ahorro_neto_estimado`` y ``costo_total_pedido``. Las columnas
            extra se ignoran.

    Returns:
        DataFrame con una fila por ``(recomendacion_id, criterio)`` -- 6 filas
        por recomendación -- y las columnas de :data:`COLUMNAS_SALIDA`, ordenado
        por ``recomendacion_id`` y luego por el orden lógico de
        :data:`ORDEN_CRITERIOS`. Ver "Contrato de la salida" en el docstring del
        módulo.

    Reglas:
        - Criterio 1, ``riesgo_quiebre_stock``: "Crítico" si
          ``stock_actual <= stock_seguridad``, "Atención" si
          ``stock_seguridad < stock_actual <= punto_reorden`` y "Sin riesgo" si
          ``stock_actual > punto_reorden``.
        - Criterio 2, ``eficiencia_cantidad_eoq``: con
          ``ratio = cantidad_recomendada / cantidad_eoq``, "Pedido muy pequeño"
          si ``ratio < RATIO_MIN - TOLERANCIA_RATIO``, "Óptima" si está dentro
          del rango (incluidas las fronteras 0.90 y 1.10) y "Pedido excesivo" si
          ``ratio > RATIO_MAX + TOLERANCIA_RATIO``.
        - Criterio 3, ``confianza_demanda``: "Alta confianza" si
          ``cv_demanda <= CV_ALTA + TOLERANCIA_CV``, "Confianza moderada" si
          ``cv_demanda <= CV_MODERADA + TOLERANCIA_CV`` y "Baja confianza
          (revisión manual)" en el resto.
        - Criterio 4, ``importancia_producto``: tabla de doble entrada
          :data:`IMPORTANCIA_POR_CLASE` sobre ``(clase_abc, clase_xyz)``.
        - Criterio 5, ``confiabilidad_proveedor``: "Confiable" si
          ``score_proveedor >= SCORE_CONFIABLE - TOLERANCIA_SCORE``, "Riesgoso"
          si ``score_proveedor < SCORE_RIESGOSO - TOLERANCIA_SCORE`` y
          "Aceptable con reservas" en el resto.
        - Criterio 6, ``oportunidad_ahorro``: "Ahorro detectado" si
          ``ahorro_neto_estimado >= costo_total_pedido * AHORRO_PCT -
          TOLERANCIA_AHORRO`` y "Sin oportunidad adicional" en el resto.

    Notas:
        - La función es pura: no accede a red, base de datos ni archivos, no
          imprime ni registra nada y **no modifica** ``recomendaciones`` (solo
          se lee y se seleccionan columnas; todo el cálculo se hace con arrays
          de numpy).
        - ``valor_numerico`` es ``None`` para ``importancia_producto`` (criterio
          categórico puro) y el valor calculado para los otros cinco criterios.
        - Orden de ejecución: (1) validar las columnas requeridas, (2) si el
          DataFrame está vacío devolver la salida vacía, (3) si hay filas
          evaluar los seis criterios.

    Raises:
        ValueError: si falta alguna columna de :data:`COLUMNAS_REQUERIDAS`,
            tenga o no filas el DataFrame.
        ValueError: si alguna fila trae una combinación ``clase_abc`` x
            ``clase_xyz`` fuera de la tabla del criterio 4.
    """


    # La validación de columnas es estricta y ocurre siempre, tenga o no filas la
    # entrada: es la política común a todos los módulos del motor.
    _verificar_columnas(recomendaciones)

    # Con las columnas ya garantizadas, un DataFrame vacío devuelve la salida
    # vacía con el mismo contrato (columnas, dtypes y categórica ordenada).
    if recomendaciones.empty:
        return _resultado_vacio()

    # Selección de las columnas que participan del cálculo. Nunca se asigna
    # sobre el argumento: la entrada no se toca.
    datos: pd.DataFrame = recomendaciones[list(COLUMNAS_REQUERIDAS)]

    recomendacion_id: np.ndarray = datos["recomendacion_id"].to_numpy(dtype=object)
    clase_abc: np.ndarray = datos["clase_abc"].to_numpy(dtype=object)
    clase_xyz: np.ndarray = datos["clase_xyz"].to_numpy(dtype=object)
    stock_actual: np.ndarray = datos["stock_actual"].to_numpy(dtype="float64")
    stock_seguridad: np.ndarray = datos["stock_seguridad"].to_numpy(dtype="float64")
    punto_reorden: np.ndarray = datos["punto_reorden"].to_numpy(dtype="float64")
    cantidad_recomendada: np.ndarray = datos["cantidad_recomendada"].to_numpy(
        dtype="float64"
    )
    cantidad_eoq: np.ndarray = datos["cantidad_eoq"].to_numpy(dtype="float64")
    cv_demanda: np.ndarray = datos["cv_demanda"].to_numpy(dtype="float64")
    score_proveedor: np.ndarray = datos["score_proveedor"].to_numpy(dtype="float64")
    ahorro_neto_estimado: np.ndarray = datos["ahorro_neto_estimado"].to_numpy(
        dtype="float64"
    )
    costo_total_pedido: np.ndarray = datos["costo_total_pedido"].to_numpy(
        dtype="float64"
    )

    # --- Criterio 1: riesgo de quiebre de stock --------------------------------
    # Los cortes son exhaustivos y mutuamente excluyentes: <= seguridad es
    # crítico, <= ROP (y por encima de la seguridad) es atención y por encima del
    # ROP es sin riesgo. Este criterio no lleva tolerancia (ver el docstring del
    # módulo).
    estados_riesgo: np.ndarray = np.select(
        [
            stock_actual <= stock_seguridad,
            stock_actual <= punto_reorden,
        ],
        [
            ESTADO_CRITICO,
            ESTADO_ATENCION,
        ],
        default=ESTADO_SIN_RIESGO,
    )

    # --- Criterio 2: eficiencia de la cantidad pedida --------------------------
    # cantidad_eoq > 0 es precondición del motor (H > 0 en eoq_rop.py): no se
    # valida aquí, igual que el resto del motor no valida rangos. El contexto
    # errstate silencia el aviso de numpy en el caso fuera de contrato (EOQ 0),
    # donde el ratio sería inf o nan.
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio: np.ndarray = cantidad_recomendada / cantidad_eoq

    # La banda tolerada [0.90 - tol, 1.10 + tol] es "Óptima" y va como default,
    # para no repetir la condición del intervalo.
    estados_eficiencia: np.ndarray = np.select(
        [
            ratio < RATIO_MIN - TOLERANCIA_RATIO,
            ratio > RATIO_MAX + TOLERANCIA_RATIO,
        ],
        [
            ESTADO_PEDIDO_PEQUENO,
            ESTADO_PEDIDO_EXCESIVO,
        ],
        default=ESTADO_OPTIMA,
    )

    # --- Criterio 3: confianza en la demanda estimada --------------------------
    # Mismos cortes (y misma tolerancia) que la clasificación XYZ del motor.
    estados_confianza: np.ndarray = np.select(
        [
            cv_demanda <= CV_ALTA + TOLERANCIA_CV,
            cv_demanda <= CV_MODERADA + TOLERANCIA_CV,
        ],
        [
            ESTADO_ALTA_CONFIANZA,
            ESTADO_CONFIANZA_MODERADA,
        ],
        default=ESTADO_BAJA_CONFIANZA,
    )

    # --- Criterio 4: importancia del producto (ABC x XYZ) ----------------------
    importancia: np.ndarray = _importancia_por_clase(clase_abc, clase_xyz)


    # --- Criterio 5: confiabilidad del proveedor -------------------------------
    # 'Aceptable con reservas' (el intervalo [60, 80)) va como default. Los
    # umbrales llevan la tolerancia en el lado inclusivo: >= 80 es confiable y
    # < 60 es riesgoso.
    estados_confiabilidad: np.ndarray = np.select(
        [
            score_proveedor >= SCORE_CONFIABLE - TOLERANCIA_SCORE,
            score_proveedor < SCORE_RIESGOSO - TOLERANCIA_SCORE,
        ],
        [
            ESTADO_CONFIABLE,
            ESTADO_RIESGOSO,
        ],
        default=ESTADO_ACEPTABLE_CON_RESERVAS,
    )

    # --- Criterio 6: oportunidad de ahorro por volumen -------------------------
    # El umbral es el 3 % del costo total del pedido, con la tolerancia restada
    # para absorber el ruido de punto flotante del corte.
    umbral_ahorro: np.ndarray = costo_total_pedido * AHORRO_PCT
    estados_ahorro: np.ndarray = np.select(
        [ahorro_neto_estimado >= umbral_ahorro - TOLERANCIA_AHORRO],
        [ESTADO_AHORRO_DETECTADO],
        default=ESTADO_SIN_OPORTUNIDAD,
    )

    # --- Combinación de los seis criterios -------------------------------------
    # Estrategia elegida: pd.concat de seis sub-DataFrames (uno por criterio), en
    # el orden de ORDEN_CRITERIOS. Ver "Estrategia de construcción de la salida"
    # en el docstring del módulo.
    resultado: pd.DataFrame = pd.concat(
        [
            _filas_de_criterio(
                recomendacion_id, CRITERIO_RIESGO, estados_riesgo, stock_actual
            ),
            _filas_de_criterio(
                recomendacion_id,
                CRITERIO_EFICIENCIA,
                estados_eficiencia,
                ratio,
            ),
            _filas_de_criterio(
                recomendacion_id, CRITERIO_CONFIANZA, estados_confianza, cv_demanda
            ),
            _filas_de_criterio(
                recomendacion_id, CRITERIO_IMPORTANCIA, importancia, None
            ),
            _filas_de_criterio(
                recomendacion_id,
                CRITERIO_CONFIABILIDAD,
                estados_confiabilidad,
                score_proveedor,
            ),
            _filas_de_criterio(
                recomendacion_id,
                CRITERIO_AHORRO,
                estados_ahorro,
                ahorro_neto_estimado,
            ),
        ],
        ignore_index=True,
    )

    # 'criterio' como categórica ordenada: así el orden de la salida sigue la
    # jerarquía de la rúbrica (1 a 6) y no el alfabético, que pondría
    # 'confiabilidad_proveedor' antes que 'oportunidad_ahorro'.
    resultado["criterio"] = pd.Categorical(
        resultado["criterio"], categories=ORDEN_CRITERIOS, ordered=True
    )

    return resultado.sort_values(
        by=["recomendacion_id", "criterio"],
        ascending=True,
        kind="mergesort",
    ).reset_index(drop=True)



def guardar_evaluaciones(
    supabase_client: "Client",
    evaluaciones: pd.DataFrame,
) -> None:
    """
    Escribe las evaluaciones en la tabla ``evaluaciones_criterios`` de Supabase.

    Filtra las columnas de :data:`COLUMNAS_SALIDA`, las convierte en una lista de
    diccionarios con ``to_dict(orient="records")`` y las inserta de una sola vez
    con ``insert``. No calcula nada: solo hace E/S.

    Args:
        supabase_client: cliente de Supabase configurado con la
            **service_role key**. La tabla tiene RLS habilitado con políticas de
            solo lectura (``db/schema.sql``), así que con la ``anon key`` el
            ``insert`` falla; toda escritura del backend pasa por
            ``service_role``, que ignora RLS.
        evaluaciones: DataFrame tal como lo devuelve
            :func:`evaluar_recomendaciones` (o cualquier DataFrame con las
            columnas de :data:`COLUMNAS_SALIDA`). Debe traer ``recomendacion_id``
            con UUID de recomendaciones ya persistidas: la columna es una clave
            foránea a ``recomendaciones.id``.

    Returns:
        None. Un DataFrame sin filas no genera ninguna petición.

    Notas:
        - Los valores de numpy (``np.float64``, ``np.int64``, ...) se convierten
          a tipos nativos antes de insertar, porque el cliente de Supabase
          serializa el cuerpo con el módulo ``json`` estándar, que no los sabe
          serializar.
        - Los ``NaN`` (y cualquier otro valor nulo: ``None``, ``pd.NA``, ``NaT``)
          se reemplazan por ``None`` para que en la base de datos queden como
          ``NULL`` y no como ``NaN``. Es el caso de ``valor_numerico`` en el
          criterio ``importancia_producto``, que siempre llega como ``None``;
          la conversión es una red de seguridad para cualquier nulo residual.
        - ``id`` y ``creado_en`` no se envían: los pone Supabase con
          ``gen_random_uuid()`` y ``now()``.
        - No modifica ``evaluaciones``.

    Raises:
        ValueError: si al DataFrame le falta alguna columna de
            :data:`COLUMNAS_SALIDA`.
        Exception: cualquier error de la API de Supabase (RLS, clave foránea
            inexistente, columna nula en un ``not null``, timeout) se propaga tal
            cual.
    """
    faltantes: list[str] = [
        columna for columna in COLUMNAS_SALIDA if columna not in evaluaciones.columns
    ]
    if faltantes:
        raise ValueError(
            "guardar_evaluaciones: a las evaluaciones les faltan las columnas "
            f"que se escriben en la tabla '{TABLA_EVALUACIONES}'; faltan: "
            f"{', '.join(faltantes)}."
        )

    seleccion: pd.DataFrame = evaluaciones[list(COLUMNAS_SALIDA)]
    if seleccion.empty:
        return

    registros: list[dict[str, object]] = [
        {columna: _valor_para_insertar(valor) for columna, valor in fila.items()}
        for fila in seleccion.to_dict(orient="records")
    ]

    supabase_client.table(TABLA_EVALUACIONES).insert(registros).execute()


def evaluar_y_guardar(
    supabase_client: "Client",
    recomendaciones: pd.DataFrame,
) -> None:
    """
    Aplica la rúbrica y guarda las evaluaciones en Supabase, en una sola llamada.

    Es una conveniencia para el llamador: equivale a
    ``guardar_evaluaciones(supabase_client, evaluar_recomendaciones(recomendaciones))``
    y existe para no tener que encadenar las dos funciones (y no confundir el
    orden de los argumentos) en los scripts y en la fase de integración. No
    agrega lógica: la evaluación la hace :func:`evaluar_recomendaciones` y la
    escritura, :func:`guardar_evaluaciones`.

    Args:
        supabase_client: cliente de Supabase configurado con la **service_role
            key** (ver :func:`guardar_evaluaciones`).
        recomendaciones: DataFrame de recomendaciones **ya persistidas**, con las
            columnas de :data:`COLUMNAS_REQUERIDAS` y con ``recomendacion_id``
            (UUID de la tabla ``recomendaciones``) asignado por el llamador.

    Returns:
        None.

    Notas:
        - Un DataFrame de recomendaciones vacío no genera ninguna petición: la
          evaluación sale vacía y el guardado la ignora.
        - Los errores de validación de :func:`evaluar_recomendaciones` y los de
          la API de Supabase se propagan tal cual.

    Raises:
        ValueError: si a ``recomendaciones`` le falta alguna columna de
            :data:`COLUMNAS_REQUERIDAS` o si trae una combinación ABC/XYZ fuera
            de la tabla del criterio 4.
    """
    evaluaciones: pd.DataFrame = evaluar_recomendaciones(recomendaciones)
    guardar_evaluaciones(supabase_client, evaluaciones)



def _importancia_por_clase(
    clase_abc: np.ndarray, clase_xyz: np.ndarray
) -> np.ndarray:
    """Aplica la tabla de doble entrada del criterio 4 a cada fila.

    Args:
        clase_abc: clases ABC ('A', 'B' o 'C'), una por recomendación.
        clase_xyz: clases XYZ ('X', 'Y' o 'Z'), una por recomendación.

    Returns:
        Array de objetos con la importancia de cada fila ('Alta', 'Media' o
        'Baja'), en el mismo orden que las entradas.

    Raises:
        ValueError: si alguna pareja (clase_abc, clase_xyz) no está en
            :data:`IMPORTANCIA_POR_CLASE`. ``estado`` es ``not null`` en la tabla
            ``evaluaciones_criterios``, así que un valor fuera de contrato se
            reporta aquí en lugar de escribir un ``NULL`` en silencio.
    """
    claves: list[tuple[object, object]] = list(
        zip(clase_abc.tolist(), clase_xyz.tolist())
    )
    desconocidas: list[tuple[object, object]] = sorted(
        {clave for clave in claves if clave not in IMPORTANCIA_POR_CLASE},
        key=repr,
    )
    if desconocidas:
        detalle = ", ".join(f"{abc!r} x {xyz!r}" for abc, xyz in desconocidas)
        raise ValueError(
            "evaluar_recomendaciones: la tabla de importancia del criterio "
            "'importancia_producto' solo admite las combinaciones A/B/C x X/Y/Z; "
            f"se encontraron: {detalle}."
        )

    return np.array([IMPORTANCIA_POR_CLASE[clave] for clave in claves], dtype=object)


def _filas_de_criterio(
    recomendacion_id: np.ndarray,
    criterio: str,
    estados: np.ndarray,
    valores: np.ndarray | None,
) -> pd.DataFrame:
    """Construye las filas de un criterio: una por recomendación.

    Args:
        recomendacion_id: identificadores de las recomendaciones, en orden.
        criterio: nombre del criterio (una de las constantes ``CRITERIO_*``).
        estados: estado de cada recomendación en ese criterio.
        valores: ``valor_numerico`` de cada recomendación, o ``None`` para el
            criterio categórico puro (``importancia_producto``), que no tiene
            valor numérico.

    Returns:
        DataFrame con las columnas de :data:`COLUMNAS_SALIDA` y una fila por
        recomendación. ``valor_numerico`` es ``float64`` cuando se pasa un array
        de valores y ``object`` lleno de ``None`` cuando ``valores`` es ``None``.
    """
    if valores is None:
        columna_valores: pd.Series = pd.Series(
            [None] * recomendacion_id.shape[0], dtype=object
        )
    else:
        columna_valores = pd.Series(valores, dtype="float64")

    return pd.DataFrame(
        {
            "recomendacion_id": pd.Series(recomendacion_id, dtype=object),
            "criterio": pd.Series([criterio] * recomendacion_id.shape[0], dtype=object),
            "estado": pd.Series(estados, dtype=object),
            "valor_numerico": columna_valores,
        }
    )


def _resultado_vacio() -> pd.DataFrame:
    """Devuelve la salida vacía, con las columnas y dtypes de la salida real.

    Returns:
        DataFrame sin filas con las columnas de :data:`COLUMNAS_SALIDA` y un
        RangeIndex vacío: ``recomendacion_id``, ``criterio`` y ``estado`` como
        ``object`` y ``valor_numerico`` como ``object`` (es la única columna que
        puede contener ``None``). ``criterio`` es la categórica ordenada con las
        categorías de :data:`ORDEN_CRITERIOS`, para que la salida vacía tenga el
        mismo contrato que la no vacía.
    """
    return pd.DataFrame(
        {
            "recomendacion_id": pd.Series(dtype=object),
            "criterio": pd.Series(
                pd.Categorical([], categories=ORDEN_CRITERIOS, ordered=True)
            ),
            "estado": pd.Series(dtype=object),
            "valor_numerico": pd.Series(dtype=object),
        }
    )



def _verificar_columnas(recomendaciones: pd.DataFrame) -> None:
    """Valida que el DataFrame traiga las columnas requeridas.

    Args:
        recomendaciones: DataFrame de entrada de :func:`evaluar_recomendaciones`.

    Raises:
        ValueError: si falta alguna columna requerida.
    """
    faltantes: list[str] = [
        columna
        for columna in COLUMNAS_REQUERIDAS
        if columna not in recomendaciones.columns
    ]
    if faltantes:
        raise ValueError(
            "evaluar_recomendaciones requiere las columnas "
            f"{', '.join(COLUMNAS_REQUERIDAS)}; faltan: {', '.join(faltantes)}."
        )


def _valor_para_insertar(valor: object) -> object:
    """Convierte una celda al valor que se envía a Supabase.

    Args:
        valor: valor de la celda tal como lo devuelve ``to_dict``.

    Returns:
        ``None`` si la celda es nula (``None``, ``NaN``, ``pd.NA``, ``NaT``) para
        que en la base de datos quede ``NULL``; en cualquier otro caso, el valor
        como escalar nativo de Python.
    """
    if _es_nulo(valor):
        return None
    return _escalar_nativo(valor)


def _es_nulo(valor: object) -> bool:
    """Indica si una celda escalar debe escribirse como ``NULL``.

    Args:
        valor: valor de la celda.

    Returns:
        ``True`` para ``None``, ``NaN``, ``pd.NA`` o ``NaT``; ``False`` para el
        resto. Se apoya en ``pd.isna``, que cubre los nulos de pandas además del
        ``None`` de Python; si el valor no es escalar, ``pd.isna`` devuelve un
        array y ``bool`` falla, así que se considera no nulo.
    """
    if valor is None:
        return True
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


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
        (``np.int64`` no es subclase de ``int``). El número no cambia: solo su
        tipo Python. Es el mismo helper que usa
        :func:`src.recomendador.guardar_recomendaciones`; se repite aquí para no
        depender de un nombre privado de otro módulo.
    """
    if isinstance(valor, np.bool_):
        return bool(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    return valor

