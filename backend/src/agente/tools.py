"""Tools de solo lectura del agente conversacional (RF-09, RF-10).

Este módulo expone las cinco funciones que el agente puede invocar para
consultar las recomendaciones ya persistidas y sus evaluaciones. Todas son
**de solo lectura**: solo hacen ``SELECT`` sobre Supabase, nunca
``INSERT``/``UPDATE``/``DELETE``. El cliente llega como primer argumento y basta
la ``anon key``: el schema habilita políticas de solo lectura para ``anon`` y
``authenticated`` (ver ``db/schema.sql``).

Las cinco tools
---------------
* :func:`buscar_recomendaciones` -- lista priorizada de recomendaciones, con
  filtro opcional por urgencia y límite.
* :func:`detalle_recomendacion` -- todos los campos de una recomendación (por
  nombre de producto) más el nombre del producto y del proveedor elegido.
* :func:`explicar_criterio` -- estado y valor de un criterio concreto de la
  recomendación de un producto.
* :func:`comparar_proveedores` -- proveedores de un producto con su score.
* :func:`resumen_prioridad_ABC_XYZ` -- conteos agregados por clase ABC/XYZ y por
  urgencia, más el ahorro neto acumulado.

Identificador de producto
-------------------------
El agente (LLM) **no** conoce los UUID: por eso las tools que piden un producto
lo identifican por ``producto_nombre`` (el ``nombre`` de ``productos``). Si hay
más de un producto con el mismo nombre se lanza :class:`ValueError` en lugar de
resolver el empate en silencio.

Urgencia
--------
La urgencia **no** es una columna de ``recomendaciones``: se calcula a partir de
``stock_actual`` (que vive en ``productos``), ``stock_seguridad`` y
``punto_reorden`` (que viven en ``recomendaciones``), con los mismos cortes que
:mod:`src.recomendador`:

* ``Crítico`` si ``stock_actual <= stock_seguridad``.
* ``Atención`` si ``stock_seguridad < stock_actual <= punto_reorden``.
* ``Sin riesgo`` si ``stock_actual > punto_reorden``.

Como ``stock_actual`` no está en ``recomendaciones``, cada tool lee también
``productos`` y combina ambas tablas en Python (con pandas). Se prefirió esto a
las relaciones embebidas de PostgREST (``select("*, productos(nombre)")``) por
dos motivos: (1) hacen falta columnas de ``productos`` además de ``nombre``
(``stock_actual``) y (2) el cliente de prueba del proyecto simula únicamente
``table(...).select(...).execute()``.

Score de proveedor
------------------
:func:`comparar_proveedores` usa la fórmula del criterio 5
(``cumplimiento * 0.6 + (100 - defectos) * 0.4``) reutilizando los pesos
:data:`~src.motor.proveedor.PESO_CUMPLIMIENTO` y
:data:`~src.motor.proveedor.PESO_CALIDAD` del motor, que son su fuente única de
verdad.

Serialización
-------------
Los valores que devuelve pandas/numpy (``np.int64``, ``np.float64``, ``pd.NA``,
``nan``, ``pd.Timestamp``...) se convierten a tipos nativos de Python (``int``,
``float``, ``str``, ``bool``, ``None``) antes de retornarlos, para que sean
serializables a JSON sin sorpresas.

Contrato de errores
-------------------
* Producto inexistente: ``None`` en las tools de objeto único y ``[]`` en las de
  lista.
* Nombre de producto duplicado: :class:`ValueError` (en las tres tools que
  identifican el producto por nombre).
* ``criterio``, ``urgencia`` o ``limite`` inválidos: :class:`ValueError`.
* Fallo de Supabase: se propaga la excepción original, sin envolverla.
"""

import math
import numbers
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from src.motor.proveedor import PESO_CALIDAD, PESO_CUMPLIMIENTO

if TYPE_CHECKING:  # pragma: no cover - solo para las anotaciones de tipo
    # El cliente se importa solo para el chequeo de tipos: así el módulo (y los
    # tests de las tools) no dependen del paquete 'supabase' en tiempo de
    # ejecución.
    from supabase import Client

__all__ = [
    "buscar_recomendaciones",
    "detalle_recomendacion",
    "explicar_criterio",
    "comparar_proveedores",
    "resumen_prioridad_ABC_XYZ",
]

# ------------------------------------------------------------------- tablas

TABLA_RECOMENDACIONES: str = "recomendaciones"
TABLA_EVALUACIONES: str = "evaluaciones_criterios"
TABLA_PRODUCTOS: str = "productos"
TABLA_PROVEEDORES: str = "proveedores"
TABLA_PRODUCTO_PROVEEDOR: str = "producto_proveedor"

# --------------------------------------------------------------- las urgencias

URGENCIA_CRITICO: str = "Crítico"
URGENCIA_ATENCION: str = "Atención"
URGENCIA_SIN_RIESGO: str = "Sin riesgo"

# Orden de prioridad de negocio (Crítico > Atención > Sin riesgo). Se usa como
# categorías de la columna 'urgencia' para que el orden sea el de prioridad y no
# el alfabético, igual que en src.recomendador.
ORDEN_URGENCIA: list[str] = [URGENCIA_CRITICO, URGENCIA_ATENCION, URGENCIA_SIN_RIESGO]
URGENCIAS_VALIDAS: tuple[str, ...] = tuple(ORDEN_URGENCIA)

# ----------------------------------------------------------------- los criterios

CRITERIO_RIESGO: str = "riesgo_quiebre_stock"
CRITERIO_EFICIENCIA: str = "eficiencia_cantidad_eoq"
CRITERIO_CONFIANZA: str = "confianza_demanda"
CRITERIO_IMPORTANCIA: str = "importancia_producto"
CRITERIO_CONFIABILIDAD: str = "confiabilidad_proveedor"
CRITERIO_AHORRO: str = "oportunidad_ahorro"

# Los 6 criterios válidos, en el orden de la rúbrica (MVP.md §10). Coincide con
# el 'check' de evaluaciones_criterios en db/schema.sql.
CRITERIOS_VALIDOS: tuple[str, ...] = (
    CRITERIO_RIESGO,
    CRITERIO_EFICIENCIA,
    CRITERIO_CONFIANZA,
    CRITERIO_IMPORTANCIA,
    CRITERIO_CONFIABILIDAD,
    CRITERIO_AHORRO,
)

# ------------------------------------------------------------------- las clases

CLASES_ABC: tuple[str, ...] = ("A", "B", "C")
CLASES_XYZ: tuple[str, ...] = ("X", "Y", "Z")


# ===================================================================== tools


def buscar_recomendaciones(
    supabase_client: "Client",
    urgencia: str | None = None,
    limite: int = 20,
) -> list[dict]:
    """
    Lista las recomendaciones priorizadas, con filtro y límite opcionales.

    Lee ``recomendaciones`` y ``productos``, calcula la urgencia de cada fila
    (ver el docstring del módulo), filtra por ``urgencia`` si se pide, ordena por
    urgencia (``Crítico`` > ``Atención`` > ``Sin riesgo``), luego por
    ``ahorro_neto_estimado`` descendente y, como desempate, por ``producto_id``
    ascendente, y devuelve como mucho ``limite`` filas.

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        urgencia: si no es ``None``, una de ``"Crítico"``, ``"Atención"`` o
            ``"Sin riesgo"``. ``None`` (default) devuelve todas.
        limite: número máximo de filas a devolver. Entero positivo; default 20.

    Returns:
        Lista de dicts (una entrada por recomendación) con las claves
        ``producto_nombre``, ``urgencia``, ``clase_abc``, ``clase_xyz``,
        ``cantidad_recomendada`` y ``ahorro_neto_estimado``. Lista vacía si no
        hay recomendaciones (o si no sobrevive ninguna al filtro).

    Raises:
        ValueError: si ``urgencia`` no es uno de los tres valores válidos (ni
            ``None``) o si ``limite`` no es un entero positivo.
        Exception: si Supabase falla (propaga la excepción original).
    """
    _validar_urgencia(urgencia)
    _validar_limite(limite)

    recomendaciones = _leer_tabla(supabase_client, TABLA_RECOMENDACIONES)
    if recomendaciones.empty:
        return []

    catalogo = _catalogo_productos(_leer_tabla(supabase_client, TABLA_PRODUCTOS))
    datos = recomendaciones.merge(catalogo, on="producto_id", how="inner")
    if datos.empty:
        return []

    datos = datos.copy()
    datos["urgencia"] = pd.Categorical(
        _marcar_urgencia(datos), categories=ORDEN_URGENCIA, ordered=True
    )

    if urgencia is not None:
        datos = datos[datos["urgencia"] == urgencia]

    datos = datos.sort_values(
        by=["urgencia", "ahorro_neto_estimado", "producto_id"],
        ascending=[True, False, True],
        kind="mergesort",
    ).head(limite)

    return [_fila_buscar(fila) for _, fila in datos.iterrows()]


def detalle_recomendacion(
    supabase_client: "Client",
    producto_nombre: str,
) -> dict | None:
    """
    Devuelve todos los campos de la recomendación de un producto, por nombre.

    Busca el producto por ``nombre`` exacto y, con su ``producto_id``, la
    recomendación asociada. Devuelve todos los campos de la recomendación más
    ``producto_nombre`` y ``proveedor_nombre`` (el del proveedor elegido).

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        producto_nombre: ``nombre`` exacto del producto (no un UUID).

    Returns:
        Dict con los campos de la recomendación más ``producto_nombre`` y
        ``proveedor_nombre``; ``None`` si el producto no existe o no tiene
        recomendación.

    Raises:
        ValueError: si hay más de un producto con ese nombre.
        Exception: si Supabase falla (propaga la excepción original).

    Notas:
        Si un producto tuviera más de una recomendación (la tabla acumula las
        corridas del motor), se devuelve la **más reciente** por
        ``fecha_generacion``.
    """
    producto = _buscar_producto(supabase_client, producto_nombre)
    if producto is None:
        return None

    recomendacion = _ultima_recomendacion(supabase_client, producto["id"])
    if recomendacion is None:
        return None

    proveedor = _buscar_proveedor(
        supabase_client, recomendacion.get("proveedor_id")
    )

    detalle: dict = {
        clave: _a_nativo(valor) for clave, valor in recomendacion.items()
    }
    detalle["producto_nombre"] = _a_nativo(producto.get("nombre"))
    detalle["proveedor_nombre"] = (
        None if proveedor is None else _a_nativo(proveedor.get("nombre"))
    )
    return detalle


def explicar_criterio(
    supabase_client: "Client",
    producto_nombre: str,
    criterio: str,
) -> dict | None:
    """
    Explica el estado y el valor de un criterio para la recomendación de un producto.

    Busca el producto por ``nombre``, su recomendación más reciente y, entre las
    evaluaciones de esa recomendación, la del ``criterio`` pedido.

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        producto_nombre: ``nombre`` exacto del producto (no un UUID).
        criterio: uno de los 6 criterios de :data:`CRITERIOS_VALIDOS`.

    Returns:
        Dict con ``producto_nombre``, ``criterio``, ``estado`` y
        ``valor_numerico``; ``None`` si el producto no existe, no tiene
        recomendación o no tiene evaluación para ese criterio.

    Raises:
        ValueError: si ``criterio`` no es uno de los 6 válidos, o si hay más de
            un producto con ese nombre.
        Exception: si Supabase falla (propaga la excepción original).
    """
    _validar_criterio(criterio)

    producto = _buscar_producto(supabase_client, producto_nombre)
    if producto is None:
        return None

    recomendacion = _ultima_recomendacion(supabase_client, producto["id"])
    if recomendacion is None:
        return None

    evaluaciones = _leer_tabla(supabase_client, TABLA_EVALUACIONES)
    if evaluaciones.empty or "criterio" not in evaluaciones.columns:
        return None

    filtradas = evaluaciones[
        (evaluaciones["recomendacion_id"] == recomendacion["id"])
        & (evaluaciones["criterio"] == criterio)
    ]
    if filtradas.empty:
        return None

    fila = filtradas.iloc[0]
    return {
        "producto_nombre": _a_nativo(producto.get("nombre")),
        "criterio": _a_nativo(fila["criterio"]),
        "estado": _a_nativo(fila["estado"]),
        "valor_numerico": _a_nativo(fila["valor_numerico"]),
    }


def comparar_proveedores(
    supabase_client: "Client",
    producto_nombre: str,
) -> list[dict]:
    """
    Compara los proveedores de un producto calculando su score.

    Busca el producto por ``nombre`` y devuelve, para cada proveedor relacionado
    en ``producto_proveedor``, su nombre, precio, lead time, cumplimiento,
    defectos y score. El score se calcula con la fórmula del criterio 5
    (``cumplimiento * 0.6 + (100 - defectos) * 0.4``).

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        producto_nombre: ``nombre`` exacto del producto (no un UUID).

    Returns:
        Lista de dicts ordenada por ``score_proveedor`` descendente y, en caso de
        empate, por ``precio_unitario`` ascendente. Cada dict tiene las claves
        ``proveedor_nombre``, ``precio_unitario``, ``lead_time_dias``,
        ``cumplimiento_entrega_pct``, ``tasa_defectos_pct`` y
        ``score_proveedor``. Lista vacía si el producto no existe o no tiene
        proveedores.

    Raises:
        ValueError: si hay más de un producto con ese nombre.
        Exception: si Supabase falla (propaga la excepción original).
    """
    producto = _buscar_producto(supabase_client, producto_nombre)
    if producto is None:
        return []

    relaciones = _leer_tabla(supabase_client, TABLA_PRODUCTO_PROVEEDOR)
    if relaciones.empty or "producto_id" not in relaciones.columns:
        return []

    relaciones = relaciones[relaciones["producto_id"] == producto["id"]]
    if relaciones.empty:
        return []

    proveedores = _leer_tabla(supabase_client, TABLA_PROVEEDORES)
    if proveedores.empty or "id" not in proveedores.columns:
        return []

    catalogo = (
        proveedores[
            ["id", "nombre", "cumplimiento_entrega_pct", "tasa_defectos_pct"]
        ]
        .rename(columns={"id": "proveedor_id", "nombre": "proveedor_nombre"})
        .drop_duplicates(subset="proveedor_id", keep="first")
    )

    combinado = relaciones.merge(catalogo, on="proveedor_id", how="inner")
    if combinado.empty:
        return []

    combinado = combinado.copy()
    # Fórmula del criterio 5, con los pesos del motor (fuente única de verdad).
    combinado["score_proveedor"] = (
        combinado["cumplimiento_entrega_pct"].astype("float64") * PESO_CUMPLIMIENTO
        + (100.0 - combinado["tasa_defectos_pct"].astype("float64")) * PESO_CALIDAD
    )

    combinado = combinado.sort_values(
        by=["score_proveedor", "precio_unitario"],
        ascending=[False, True],
        kind="mergesort",
    )

    return [_fila_proveedor(fila) for _, fila in combinado.iterrows()]


def resumen_prioridad_ABC_XYZ(supabase_client: "Client") -> dict:
    """
    Agrega las recomendaciones por clase ABC, clase XYZ y urgencia.

    Lee ``recomendaciones`` y ``productos`` (para calcular la urgencia) y cuenta
    sobre el resultado.

    Args:
        supabase_client: cliente de Supabase (solo lectura).

    Returns:
        Dict con ``total_recomendaciones`` (int), ``por_clase_abc`` (``A``/``B``/
        ``C``), ``por_clase_xyz`` (``X``/``Y``/``Z``), ``por_urgencia``
        (``"Crítico"``/``"Atención"``/``"Sin riesgo"``), ``por_combinacion`` (las
        9 combinaciones: ``AX``, ``AY``, ``AZ``, ``BX``, ..., ``CZ``) y
        ``suma_ahorro_neto`` (float). Con la base vacía, todos los conteos son 0
        y ``suma_ahorro_neto`` es ``0.0``.

    Raises:
        Exception: si Supabase falla (propaga la excepción original).
    """
    recomendaciones = _leer_tabla(supabase_client, TABLA_RECOMENDACIONES)
    if recomendaciones.empty:
        return _resumen_vacio()

    catalogo = _catalogo_productos(_leer_tabla(supabase_client, TABLA_PRODUCTOS))
    datos = recomendaciones.merge(catalogo, on="producto_id", how="inner")
    if datos.empty:
        return _resumen_vacio()

    datos = datos.copy()
    datos["urgencia"] = _marcar_urgencia(datos)

    conteo_abc = datos["clase_abc"].value_counts()
    conteo_xyz = datos["clase_xyz"].value_counts()
    conteo_urgencia = datos["urgencia"].value_counts()
    combinacion = datos["clase_abc"].astype(str) + datos["clase_xyz"].astype(str)
    conteo_combinacion = combinacion.value_counts()

    return {
        "total_recomendaciones": int(len(datos)),
        "por_clase_abc": {
            clase: int(conteo_abc.get(clase, 0)) for clase in CLASES_ABC
        },
        "por_clase_xyz": {
            clase: int(conteo_xyz.get(clase, 0)) for clase in CLASES_XYZ
        },
        "por_urgencia": {
            urgencia: int(conteo_urgencia.get(urgencia, 0))
            for urgencia in ORDEN_URGENCIA
        },
        "por_combinacion": {
            f"{abc}{xyz}": int(conteo_combinacion.get(f"{abc}{xyz}", 0))
            for abc in CLASES_ABC
            for xyz in CLASES_XYZ
        },
        "suma_ahorro_neto": float(
            datos["ahorro_neto_estimado"].astype("float64").sum()
        ),
    }


# ================================================================== internos


def _leer_tabla(supabase_client: "Client", tabla: str) -> pd.DataFrame:
    """
    Lee una tabla completa de Supabase y la devuelve como DataFrame.

    Es la única operación de E/S del módulo (un ``SELECT *``). Si la tabla no
    tiene filas, devuelve un DataFrame vacío (sin columnas), de modo que los
    llamadores puedan cortar antes de indexar columnas.

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        tabla: nombre de la tabla a leer.

    Returns:
        DataFrame con una fila por registro; vacío si no hay registros.

    Raises:
        Exception: si Supabase falla (propaga la excepción original).
    """
    respuesta = supabase_client.table(tabla).select("*").execute()
    filas = respuesta.data
    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas)


def _catalogo_productos(productos: pd.DataFrame) -> pd.DataFrame:
    """
    Proyecta ``productos`` a ``producto_id``/``producto_nombre``/``stock_actual``.

    Solo se conservan las tres columnas que necesitan las tools que cruzan
    ``recomendaciones`` con ``productos`` (el nombre para mostrarlo y el stock
    para calcular la urgencia). Si ``productos`` llega vacío o sin las columnas
    esperadas, devuelve un DataFrame vacío con esas tres columnas, para que el
    ``merge`` posterior no falle.

    Args:
        productos: DataFrame de la tabla ``productos`` (columnas de la base).

    Returns:
        DataFrame con ``producto_id``, ``producto_nombre`` y ``stock_actual``,
        sin duplicados por ``producto_id``.
    """
    columnas = ["producto_id", "producto_nombre", "stock_actual"]
    if productos.empty or not {"id", "nombre", "stock_actual"}.issubset(
        productos.columns
    ):
        return pd.DataFrame(columns=columnas)
    return (
        productos[["id", "nombre", "stock_actual"]]
        .rename(columns={"id": "producto_id", "nombre": "producto_nombre"})
        .drop_duplicates(subset="producto_id", keep="first")
    )


def _marcar_urgencia(datos: pd.DataFrame) -> np.ndarray:
    """
    Marca la urgencia de cada fila combinada, con los cortes del recomendador.

    Espera un DataFrame que ya tenga ``stock_actual`` (de ``productos``),
    ``stock_seguridad`` y ``punto_reorden`` (de ``recomendaciones``), es decir el
    resultado de cruzar ambas tablas.

    Args:
        datos: DataFrame con las tres columnas de stock.

    Returns:
        Array de numpy (dtype object) con ``Crítico`` / ``Atención`` /
        ``Sin riesgo``.
    """
    stock_actual = datos["stock_actual"].to_numpy(dtype="float64")
    stock_seguridad = datos["stock_seguridad"].to_numpy(dtype="float64")
    punto_reorden = datos["punto_reorden"].to_numpy(dtype="float64")
    return np.select(
        [stock_actual <= stock_seguridad, stock_actual <= punto_reorden],
        [URGENCIA_CRITICO, URGENCIA_ATENCION],
        default=URGENCIA_SIN_RIESGO,
    )


def _resumen_vacio() -> dict:
    """
    Devuelve el resumen con todos los conteos en 0 (base vacía).

    Returns:
        Dict con la misma estructura que :func:`resumen_prioridad_ABC_XYZ`, con
        todos los conteos en ``0`` y ``suma_ahorro_neto`` en ``0.0``.
    """
    return {
        "total_recomendaciones": 0,
        "por_clase_abc": {clase: 0 for clase in CLASES_ABC},
        "por_clase_xyz": {clase: 0 for clase in CLASES_XYZ},
        "por_urgencia": {urgencia: 0 for urgencia in ORDEN_URGENCIA},
        "por_combinacion": {
            f"{abc}{xyz}": 0 for abc in CLASES_ABC for xyz in CLASES_XYZ
        },
        "suma_ahorro_neto": 0.0,
    }


def _fila_buscar(fila: pd.Series) -> dict:
    """
    Proyecta una fila combinada a la salida de :func:`buscar_recomendaciones`.

    Args:
        fila: fila con ``producto_nombre``, ``urgencia``, ``clase_abc``,
            ``clase_xyz``, ``cantidad_recomendada`` y ``ahorro_neto_estimado``.

    Returns:
        Dict con esas seis claves, con valores nativos de Python.
    """
    return {
        "producto_nombre": _a_nativo(fila["producto_nombre"]),
        "urgencia": _a_nativo(fila["urgencia"]),
        "clase_abc": _a_nativo(fila["clase_abc"]),
        "clase_xyz": _a_nativo(fila["clase_xyz"]),
        "cantidad_recomendada": _a_nativo(fila["cantidad_recomendada"]),
        "ahorro_neto_estimado": _a_nativo(fila["ahorro_neto_estimado"]),
    }


def _fila_proveedor(fila: pd.Series) -> dict:
    """
    Proyecta una fila combinada a la salida de :func:`comparar_proveedores`.

    Args:
        fila: fila con los datos del proveedor y su score ya calculado.

    Returns:
        Dict con ``proveedor_nombre``, ``precio_unitario``, ``lead_time_dias``,
        ``cumplimiento_entrega_pct``, ``tasa_defectos_pct`` y
        ``score_proveedor``, con valores nativos de Python.
    """
    return {
        "proveedor_nombre": _a_nativo(fila["proveedor_nombre"]),
        "precio_unitario": _a_nativo(fila["precio_unitario"]),
        "lead_time_dias": _a_nativo(fila["lead_time_dias"]),
        "cumplimiento_entrega_pct": _a_nativo(fila["cumplimiento_entrega_pct"]),
        "tasa_defectos_pct": _a_nativo(fila["tasa_defectos_pct"]),
        "score_proveedor": _a_nativo(fila["score_proveedor"]),
    }


def _buscar_producto(supabase_client: "Client", producto_nombre: str) -> dict | None:
    """
    Devuelve la fila del producto cuyo ``nombre`` coincide exactamente.

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        producto_nombre: nombre exacto a buscar.

    Returns:
        Dict con la fila del producto, o ``None`` si no existe.

    Raises:
        ValueError: si hay más de un producto con ese nombre (el nombre se usa
            como identificador y un empate sería ambiguo).
    """
    productos = _leer_tabla(supabase_client, TABLA_PRODUCTOS)
    if productos.empty or "nombre" not in productos.columns:
        return None

    coincidencias = productos[productos["nombre"] == producto_nombre]
    if coincidencias.empty:
        return None
    if len(coincidencias) > 1:
        raise ValueError(
            f"Hay {len(coincidencias)} productos con el nombre "
            f"'{producto_nombre}': el nombre debe ser único para poder "
            f"identificar el producto."
        )
    return coincidencias.iloc[0].to_dict()


def _ultima_recomendacion(
    supabase_client: "Client", producto_id: object
) -> dict | None:
    """
    Devuelve la recomendación más reciente de un producto.

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        producto_id: ``producto_id`` de la recomendación buscada.

    Returns:
        Dict con la fila de la recomendación más reciente por
        ``fecha_generacion``, o ``None`` si el producto no tiene recomendaciones.
    """
    recomendaciones = _leer_tabla(supabase_client, TABLA_RECOMENDACIONES)
    if recomendaciones.empty or "producto_id" not in recomendaciones.columns:
        return None

    filtradas = recomendaciones[recomendaciones["producto_id"] == producto_id]
    if filtradas.empty:
        return None
    if "fecha_generacion" in filtradas.columns:
        filtradas = filtradas.sort_values(
            by="fecha_generacion", ascending=False, kind="mergesort"
        )
    return filtradas.iloc[0].to_dict()


def _buscar_proveedor(
    supabase_client: "Client", proveedor_id: object
) -> dict | None:
    """
    Devuelve la fila del proveedor con ese ``id``.

    Args:
        supabase_client: cliente de Supabase (solo lectura).
        proveedor_id: ``id`` del proveedor buscado.

    Returns:
        Dict con la fila del proveedor, o ``None`` si no existe (o si
        ``proveedor_id`` es ``None``).
    """
    if proveedor_id is None:
        return None

    proveedores = _leer_tabla(supabase_client, TABLA_PROVEEDORES)
    if proveedores.empty or "id" not in proveedores.columns:
        return None

    coincidencias = proveedores[proveedores["id"] == proveedor_id]
    if coincidencias.empty:
        return None
    return coincidencias.iloc[0].to_dict()


def _a_nativo(valor: object) -> object:
    """
    Convierte un escalar de pandas/numpy a un tipo nativo de Python.

    Los valores que devuelve pandas/numpy (``np.int64``, ``np.float64``,
    ``np.str_``, ``np.bool_``, ``pd.NA``, ``nan``, ``pd.Timestamp``...) no son
    serializables a JSON por sí mismos. Esta función normaliza:

    * Escalares de numpy -> ``int``/``float``/``str``/``bool`` (vía ``.item()``).
    * ``nan`` (float) -> ``None``.
    * ``pd.NA``/``NaT``/``None`` -> ``None``.
    * ``Decimal`` -> ``float``.
    * ``pd.Timestamp`` -> ``str`` en ISO 8601.
    * ``int``/``str``/``bool`` -> se devuelven tal cual.

    Args:
        valor: valor a normalizar.

    Returns:
        El valor convertido a un tipo nativo de Python (o ``None``).
    """
    if valor is None:
        return None
    if isinstance(valor, np.generic):
        valor = valor.item()
    if isinstance(valor, bool):
        return bool(valor)
    if isinstance(valor, float):
        return None if math.isnan(valor) else float(valor)
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        return valor
    return valor


def _validar_urgencia(urgencia: str | None) -> None:
    """
    Valida el argumento ``urgencia`` de :func:`buscar_recomendaciones`.

    Args:
        urgencia: valor recibido (``None`` o una de las tres urgencias).

    Raises:
        ValueError: si no es ``None`` ni uno de :data:`URGENCIAS_VALIDAS`.
    """
    if urgencia is not None and urgencia not in URGENCIAS_VALIDAS:
        raise ValueError(
            f"urgencia debe ser None o una de {URGENCIAS_VALIDAS}; "
            f"recibido: {urgencia!r}."
        )


def _validar_limite(limite: int) -> None:
    """
    Valida el argumento ``limite`` de :func:`buscar_recomendaciones`.

    Args:
        limite: valor recibido.

    Raises:
        ValueError: si no es un entero positivo (los ``bool`` no cuentan como
            entero aquí: ``True``/``False`` no son límites válidos).
    """
    if (
        isinstance(limite, bool)
        or not isinstance(limite, numbers.Integral)
        or limite < 1
    ):
        raise ValueError(f"limite debe ser un entero positivo; recibido: {limite!r}.")


def _validar_criterio(criterio: str) -> None:
    """
    Valida el argumento ``criterio`` de :func:`explicar_criterio`.

    Args:
        criterio: valor recibido.

    Raises:
        ValueError: si no es uno de los 6 criterios de :data:`CRITERIOS_VALIDOS`.
    """
    if criterio not in CRITERIOS_VALIDOS:
        raise ValueError(
            f"criterio debe ser uno de {CRITERIOS_VALIDOS}; recibido: {criterio!r}."
        )
