"""Tests unitarios del orquestador de recomendaciones (motor OR).

Se prueba la función pura ``src.recomendador.calcular_recomendaciones`` (incluida
la propagación de los parámetros de configuración a cada módulo del motor) y, con
un cliente de Supabase falso en memoria, ``generar_recomendaciones`` (la lectura
de las cuatro tablas de datos y de ``parametros_configuracion``). No se toca red,
base de datos ni archivos. ``guardar_recomendaciones`` sí escribe en Supabase y se
cubre en la fase de integración, con el cliente mockeado.
"""

import inspect

import numpy as np
import pandas as pd
import pytest

from src.config import PARAMETROS_DEFAULT
from src.motor.proveedor import calcular_score_proveedor
from src.recomendador import (
    COLUMNAS_HISTORIAL,
    COLUMNAS_NO_NULAS,
    COLUMNAS_PRODUCTOS,
    COLUMNAS_PRODUCTO_PROVEEDOR,
    COLUMNAS_PROVEEDORES,
    COLUMNAS_SALIDA,
    ORDEN_URGENCIA,
    URGENCIA_ATENCION,
    URGENCIA_CRITICO,
    URGENCIA_SIN_RIESGO,
    calcular_recomendaciones,
    generar_recomendaciones,
)

# Columnas de la salida, escritas explícitamente para que el contrato quede
# fijado en el test y no se derive de la constante del módulo.
COLUMNAS_ESPERADAS: tuple[str, ...] = (
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

# ------------------------------------------------------------------ utilidades


def _producto(
    producto_id: str,
    *,
    costo_unitario: float = 10.0,
    stock_actual: float = 0.0,
    costo_ordenar: float = 50.0,
    costo_mantener_pct_anual: float = 20.0,
    nombre: str | None = None,
    categoria: str = "General",
) -> dict:
    """Fila del catálogo, con los nombres de columna que espera el motor."""
    return {
        "producto_id": producto_id,
        "nombre": f"Producto {producto_id}" if nombre is None else nombre,
        "categoria": categoria,
        "costo_unitario": costo_unitario,
        "stock_actual": stock_actual,
        "costo_ordenar": costo_ordenar,
        "costo_mantener_pct_anual": costo_mantener_pct_anual,
    }


def _proveedor(
    proveedor_id: str,
    *,
    cumplimiento: float = 90.0,
    defectos: float = 5.0,
    nombre: str | None = None,
) -> dict:
    """Fila del catálogo de proveedores.

    Con los defaults (90, 5) el score es 90 * 0.6 + 95 * 0.4 = 92.
    """
    return {
        "proveedor_id": proveedor_id,
        "proveedor_nombre": f"Proveedor {proveedor_id}" if nombre is None else nombre,
        "cumplimiento_entrega_pct": cumplimiento,
        "tasa_defectos_pct": defectos,
    }


def _relacion(
    producto_id: str,
    proveedor_id: str,
    *,
    precio: float = 12.0,
    lead_time: int = 15,
    umbral: float | None = None,
    descuento: float | None = None,
) -> dict:
    """Fila de producto_proveedor. Umbral y descuento nulos = sin descuento."""
    return {
        "producto_id": producto_id,
        "proveedor_id": proveedor_id,
        "precio_unitario": precio,
        "lead_time_dias": lead_time,
        "cantidad_umbral_descuento": umbral,
        "descuento_pct": descuento,
    }


def _historial(producto_id: str, cantidades: list[float]) -> list[dict]:
    """Filas de historial de un producto, una por periodo mensual de 2025."""
    return [
        {
            "producto_id": producto_id,
            "periodo": f"2025-{mes:02d}-01",
            "cantidad_demandada": float(cantidad),
        }
        for mes, cantidad in enumerate(cantidades, start=1)
    ]


def _dataframes(
    productos: list[dict],
    proveedores: list[dict],
    relaciones: list[dict],
    historial: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Empaqueta las cuatro entradas de ``calcular_recomendaciones``."""
    return (
        pd.DataFrame(productos, columns=list(COLUMNAS_PRODUCTOS)),
        pd.DataFrame(proveedores, columns=list(COLUMNAS_PROVEEDORES)),
        pd.DataFrame(relaciones, columns=list(COLUMNAS_PRODUCTO_PROVEEDOR)),
        pd.DataFrame(historial, columns=list(COLUMNAS_HISTORIAL)),
    )


def _calcular(
    entrada: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame],
    **parametros: object,
) -> pd.DataFrame:
    """Llama al orquestador con las cuatro entradas desempaquetadas."""
    return calcular_recomendaciones(*entrada, **parametros)


def _urgencia_esperada(
    stock_actual: float, stock_seguridad: float, punto_reorden: float
) -> str:
    """Regla de urgencia según la rúbrica, escrita aparte del módulo."""
    if stock_actual <= stock_seguridad:
        return URGENCIA_CRITICO
    if stock_actual <= punto_reorden:
        return URGENCIA_ATENCION
    return URGENCIA_SIN_RIESGO


# ---------------------------------------------------------------- escenarios


def _escenario_simple(
    *,
    demanda: float = 300.0,
    periodos: int = 6,
    stock_actual: float = 0.0,
    lead_time: int = 15,
    precio: float = 12.0,
    umbral: float | None = None,
    descuento: float | None = None,
    costo_unitario: float = 10.0,
    costo_ordenar: float = 50.0,
    costo_mantener_pct_anual: float = 20.0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Un producto ('P001') con demanda plana y un proveedor ('PR1').

    Con los defaults y los parámetros por defecto del motor (12 periodos/año,
    30 días/periodo, 20 % de margen): demanda_estimada = 300, H = 2,
    EOQ = sqrt(2 * 300 * 12 * 50 / 2) ~ 424.26, SS = 30 y ROP = 180. El producto
    es clase X (CV = 0) y, al tener un descuento declarado que su EOQ no alcanza,
    sube el pedido al umbral.
    """
    return _dataframes(
        productos=[
            _producto(
                "P001",
                costo_unitario=costo_unitario,
                stock_actual=stock_actual,
                costo_ordenar=costo_ordenar,
                costo_mantener_pct_anual=costo_mantener_pct_anual,
            )
        ],
        proveedores=[_proveedor("PR1")],
        relaciones=[
            _relacion(
                "P001",
                "PR1",
                precio=precio,
                lead_time=lead_time,
                umbral=umbral,
                descuento=descuento,
            )
        ],
        historial=_historial("P001", [demanda] * periodos),
    )


def _escenario_tres_productos() -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    """Tres productos, uno por franja de urgencia, con la misma familia de proveedores.

    * P001: demanda plana de 300 y stock 0 -> Crítico; su descuento por volumen
      le da ahorro. Tiene dos proveedores con el mismo score (92) y distinto
      precio, así que gana PR1 (12.0 y lead time 15) y no PR2 (15.0 y 20).
    * P002: demanda errática (CV ~ 1.095 -> clase Z) con media 250; stock 100
      contra SS = 33.33 y ROP = 200 -> Atención. Sin descuento -> ahorro 0.
    * P003: demanda plana de 50, stock 500 contra ROP = 40 -> Sin riesgo.
    """
    return _dataframes(
        productos=[
            _producto(
                "P001",
                costo_unitario=10.0,
                stock_actual=0.0,
                costo_ordenar=50.0,
                costo_mantener_pct_anual=20.0,
            ),
            _producto(
                "P002",
                costo_unitario=20.0,
                stock_actual=100.0,
                costo_ordenar=40.0,
                costo_mantener_pct_anual=25.0,
            ),
            _producto(
                "P003",
                costo_unitario=5.0,
                stock_actual=500.0,
                costo_ordenar=30.0,
                costo_mantener_pct_anual=15.0,
            ),
        ],
        proveedores=[
            _proveedor("PR1"),
            _proveedor("PR2"),
        ],
        relaciones=[
            _relacion(
                "P001", "PR1", precio=12.0, lead_time=15, umbral=500.0, descuento=5.0
            ),
            _relacion("P001", "PR2", precio=15.0, lead_time=20),
            _relacion("P002", "PR2", precio=15.0, lead_time=20),
            _relacion("P003", "PR2", precio=15.0, lead_time=20),
        ],
        historial=(
            _historial("P001", [300.0] * 6)
            + _historial("P002", [0.0, 500.0, 0.0, 500.0, 0.0, 500.0])
            + _historial("P003", [50.0] * 6)
        ),
    )


# ------------------------------------------------------- contrato de la salida


def test_salida_tiene_las_columnas_esperadas_y_la_urgencia_categorica_ordenada():
    resultado = _calcular(_escenario_simple())

    assert list(resultado.columns) == list(COLUMNAS_ESPERADAS)
    assert list(COLUMNAS_SALIDA) == list(COLUMNAS_ESPERADAS)
    assert isinstance(resultado["urgencia"].dtype, pd.CategoricalDtype)
    assert resultado["urgencia"].cat.ordered is True
    assert list(resultado["urgencia"].cat.categories) == ORDEN_URGENCIA
    # La salida se reindexa: el índice es un RangeIndex desde 0.
    assert resultado.index.tolist() == list(range(len(resultado)))


def test_una_fila_por_producto_valido_con_las_metricas_del_motor():
    resultado = _calcular(_escenario_simple())
    fila = resultado.iloc[0]

    assert resultado.shape[0] == 1
    assert fila["producto_id"] == "P001"
    assert fila["demanda_estimada"] == pytest.approx(300.0)
    assert fila["cv_demanda"] == pytest.approx(0.0)
    assert fila["clase_xyz"] == "X"
    # Un catálogo de un solo producto se clasifica 'A' (caso degenerado de abc.py).
    assert fila["clase_abc"] == "A"
    assert fila["cantidad_eoq"] == pytest.approx(
        np.sqrt(2.0 * 300.0 * 12.0 * 50.0 / 2.0)
    )
    assert fila["stock_seguridad"] == pytest.approx((300.0 / 30.0) * 15.0 * 0.20)
    assert fila["punto_reorden"] == pytest.approx((300.0 / 30.0) * 15.0 * 1.20)
    assert fila["lead_time_dias"] == 15
    assert fila["precio_unitario"] == pytest.approx(12.0)
    assert fila["score_proveedor"] == pytest.approx(92.0)
    assert fila["stock_actual"] == pytest.approx(0.0)
    assert fila["costo_unitario"] == pytest.approx(10.0)
    assert fila["costo_ordenar"] == pytest.approx(50.0)
    assert fila["costo_mantener_pct_anual"] == pytest.approx(20.0)
    # Sin descuento declarado el pedido es el EOQ y no hay ahorro.
    assert fila["cantidad_recomendada"] == pytest.approx(fila["cantidad_eoq"])
    assert fila["ahorro_bruto"] == pytest.approx(0.0)
    assert fila["costo_extra_mantener"] == pytest.approx(0.0)
    assert fila["ahorro_neto_estimado"] == pytest.approx(0.0)
    assert fila["estado_ahorro"] == "Sin oportunidad adicional"
    assert fila["costo_total_pedido"] == pytest.approx(
        fila["cantidad_recomendada"] * 12.0
    )


def test_el_descuento_por_volumen_sube_el_pedido_y_descuenta_el_costo_extra():
    resultado = _calcular(_escenario_simple(umbral=500.0, descuento=5.0))
    fila = resultado.iloc[0]

    eoq = np.sqrt(2.0 * 300.0 * 12.0 * 50.0 / 2.0)
    assert fila["cantidad_eoq"] == pytest.approx(eoq)
    # El EOQ no alcanza el umbral: el pedido sube hasta él.
    assert fila["cantidad_recomendada"] == pytest.approx(500.0)
    assert fila["ahorro_bruto"] == pytest.approx(500.0 * 12.0 * 0.05)
    assert fila["costo_extra_mantener"] == pytest.approx(
        (500.0 - eoq) * 10.0 * 0.20 / 12.0
    )
    assert fila["ahorro_neto_estimado"] == pytest.approx(
        fila["ahorro_bruto"] - fila["costo_extra_mantener"]
    )
    assert fila["costo_total_pedido"] == pytest.approx(500.0 * 12.0)
    # 287.38 de ahorro contra un umbral de decisión de 180 (3 % del pedido).
    assert fila["estado_ahorro"] == "Ahorro detectado"


def test_sin_nulos_en_las_columnas_obligatorias():
    resultado = _calcular(_escenario_tres_productos())

    assert not resultado[list(COLUMNAS_NO_NULAS)].isna().any().any()
    # cv_demanda y clase_xyz tampoco: los productos sin CV calculable se excluyen
    # antes (test_excluye_productos_con_cv_no_calculable), así que COLUMNAS_NO_NULAS
    # no necesita incluirlas para satisfacer el 'not null' de la tabla.
    assert resultado["cv_demanda"].notna().all()
    assert resultado["clase_xyz"].notna().all()


def test_umbral_y_descuento_pueden_ser_nan_sin_que_falle_el_calculo():
    resultado = _calcular(_escenario_tres_productos())
    con_descuento = resultado["producto_id"] == "P001"
    sin_descuento = resultado.loc[~con_descuento]

    assert resultado.loc[con_descuento, "descuento_pct"].notna().all()
    assert resultado.loc[con_descuento, "cantidad_umbral_descuento"].notna().all()
    assert sin_descuento["descuento_pct"].isna().all()
    assert sin_descuento["cantidad_umbral_descuento"].isna().all()
    # El nulo no impide calcular: pedido igual al EOQ y sin oportunidad de ahorro.
    assert (
        sin_descuento["cantidad_recomendada"] == sin_descuento["cantidad_eoq"]
    ).all()
    assert (sin_descuento["ahorro_neto_estimado"] == 0.0).all()
    assert (sin_descuento["estado_ahorro"] == "Sin oportunidad adicional").all()


# --------------------------------------------------------- productos excluidos


def test_excluye_productos_sin_historial_suficiente_o_sin_proveedor():
    entrada = list(_escenario_tres_productos())
    # P004: aparece en el catálogo y tiene proveedor, pero un solo periodo.
    # P005: tiene dos periodos, pero ninguna fila en producto_proveedor.
    entrada[0] = pd.concat(
        [
            entrada[0],
            pd.DataFrame(
                [_producto("P004"), _producto("P005")],
                columns=list(COLUMNAS_PRODUCTOS),
            ),
        ],
        ignore_index=True,
    )
    entrada[2] = pd.concat(
        [
            entrada[2],
            pd.DataFrame(
                [_relacion("P004", "PR2", precio=15.0, lead_time=20)],
                columns=list(COLUMNAS_PRODUCTO_PROVEEDOR),
            ),
        ],
        ignore_index=True,
    )
    entrada[3] = pd.concat(
        [
            entrada[3],
            pd.DataFrame(
                _historial("P004", [10.0]) + _historial("P005", [10.0, 20.0]),
                columns=list(COLUMNAS_HISTORIAL),
            ),
        ],
        ignore_index=True,
    )

    resultado = _calcular(tuple(entrada))

    assert sorted(resultado["producto_id"]) == ["P001", "P002", "P003"]


def test_sin_productos_validos_devuelve_la_salida_vacia_con_el_mismo_contrato():
    sin_relaciones = _dataframes(
        productos=[_producto("P001")],
        proveedores=[_proveedor("PR1")],
        relaciones=[],
        historial=_historial("P001", [10.0, 20.0]),
    )
    sin_datos = _dataframes(
        productos=[], proveedores=[], relaciones=[], historial=[]
    )

    for entrada in (sin_relaciones, sin_datos):
        resultado = _calcular(entrada)
        assert resultado.empty
        assert list(resultado.columns) == list(COLUMNAS_ESPERADAS)
        assert isinstance(resultado["urgencia"].dtype, pd.CategoricalDtype)
        assert list(resultado["urgencia"].cat.categories) == ORDEN_URGENCIA


def test_excluye_productos_con_cv_no_calculable():
    # Un producto con 6 periodos de demanda cero tiene media 0: xyz.py no puede
    # calcular su CV y devuelve cv y clase nulos. Se excluye en silencio (la tabla
    # 'recomendaciones' exige cv_demanda NOT NULL) en lugar de provocar un error
    # más adelante, en la validación de nulos.
    entrada = _dataframes(
        productos=[_producto("P001", stock_actual=0.0), _producto("P002")],
        proveedores=[_proveedor("PR1")],
        relaciones=[_relacion("P001", "PR1"), _relacion("P002", "PR1")],
        historial=_historial("P001", [300.0] * 6) + _historial("P002", [0.0] * 6),
    )

    resultado = _calcular(entrada)

    assert resultado["producto_id"].tolist() == ["P001"]
    assert resultado["cv_demanda"].notna().all()

    # Si todos los productos quedan fuera por la misma razón, la salida es la
    # vacía del contrato, sin excepción.
    solo_sin_cv = _dataframes(
        productos=[_producto("P002")],
        proveedores=[_proveedor("PR1")],
        relaciones=[_relacion("P002", "PR1")],
        historial=_historial("P002", [0.0] * 6),
    )

    vacio = _calcular(solo_sin_cv)

    assert vacio.empty
    assert list(vacio.columns) == list(COLUMNAS_ESPERADAS)


# --------------------------------------------------------- proveedor elegido


def test_elige_el_proveedor_de_mayor_score_aunque_sea_mas_caro():
    entrada = _dataframes(
        productos=[_producto("P001")],
        proveedores=[
            _proveedor("PR_CONFIABLE", cumplimiento=90.0, defectos=5.0),  # 92
            _proveedor("PR_RIESGOSO", cumplimiento=70.0, defectos=10.0),  # 78
        ],
        relaciones=[
            _relacion("P001", "PR_CONFIABLE", precio=20.0, lead_time=10),
            _relacion("P001", "PR_RIESGOSO", precio=5.0, lead_time=10),
        ],
        historial=_historial("P001", [300.0] * 6),
    )

    fila = _calcular(entrada).set_index("producto_id").loc["P001"]

    assert fila["proveedor_id"] == "PR_CONFIABLE"
    assert fila["proveedor_nombre"] == "Proveedor PR_CONFIABLE"
    assert fila["score_proveedor"] == pytest.approx(92.0)
    assert fila["precio_unitario"] == pytest.approx(20.0)


def test_con_el_mismo_score_elige_el_de_menor_precio():
    # El proveedor barato aparece segundo en producto_proveedor: si ganara el
    # orden de entrada en lugar del precio, el test fallaría.
    entrada = _dataframes(
        productos=[_producto("P001")],
        proveedores=[_proveedor("PR_CARO"), _proveedor("PR_BARATO")],
        relaciones=[
            _relacion("P001", "PR_CARO", precio=30.0, lead_time=10),
            _relacion("P001", "PR_BARATO", precio=10.0, lead_time=10),
        ],
        historial=_historial("P001", [300.0] * 6),
    )

    fila = _calcular(entrada).set_index("producto_id").loc["P001"]

    assert fila["score_proveedor"] == pytest.approx(92.0)
    assert fila["proveedor_id"] == "PR_BARATO"
    assert fila["precio_unitario"] == pytest.approx(10.0)


def test_cada_producto_usa_el_lead_time_de_su_proveedor_elegido():
    resultado = _calcular(_escenario_tres_productos()).set_index("producto_id")

    assert resultado.loc["P001", "lead_time_dias"] == 15
    assert resultado.loc["P002", "lead_time_dias"] == 20
    assert resultado.loc["P003", "lead_time_dias"] == 20
    assert resultado.loc["P001", "punto_reorden"] == pytest.approx(
        (300.0 / 30.0) * 15.0 * 1.20
    )
    assert resultado.loc["P002", "punto_reorden"] == pytest.approx(
        (250.0 / 30.0) * 20.0 * 1.20
    )
    assert resultado.loc["P002", "clase_xyz"] == "Z"
    assert resultado.loc["P002", "cv_demanda"] == pytest.approx(
        np.std([0.0, 500.0, 0.0, 500.0, 0.0, 500.0], ddof=1) / 250.0
    )


# -------------------------------------------------------------------- urgencia


@pytest.mark.parametrize(
    ("stock_actual", "urgencia_esperada"),
    [
        (0.0, URGENCIA_CRITICO),
        (30.0, URGENCIA_CRITICO),  # frontera: stock_actual == stock_seguridad
        (30.5, URGENCIA_ATENCION),
        (180.0, URGENCIA_ATENCION),  # frontera: stock_actual == punto_reorden
        (181.0, URGENCIA_SIN_RIESGO),
    ],
)
def test_urgencia_en_las_tres_franjas_y_en_sus_fronteras(
    stock_actual: float, urgencia_esperada: str
):
    # Con demanda 300 y lead time 15: SS = 30 y ROP = 180.
    resultado = _calcular(_escenario_simple(stock_actual=stock_actual))
    fila = resultado.iloc[0]

    assert fila["stock_seguridad"] == pytest.approx(30.0)
    assert fila["punto_reorden"] == pytest.approx(180.0)
    assert fila["stock_actual"] == pytest.approx(stock_actual)
    assert fila["urgencia"] == urgencia_esperada


def test_la_urgencia_marca_todas_las_filas_sin_filtrar_ninguna():
    resultado = _calcular(_escenario_tres_productos())

    # Los tres productos siguen en la salida, uno por franja de urgencia.
    assert resultado["producto_id"].tolist() == ["P001", "P002", "P003"]
    assert resultado["urgencia"].tolist() == [
        URGENCIA_CRITICO,
        URGENCIA_ATENCION,
        URGENCIA_SIN_RIESGO,
    ]
    for _, fila in resultado.iterrows():
        assert fila["urgencia"] == _urgencia_esperada(
            fila["stock_actual"], fila["stock_seguridad"], fila["punto_reorden"]
        )


# --------------------------------------------------------------------- orden


def _escenario_para_orden() -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    """Cuatro productos que fuerzan los dos primeros criterios de orden.

    P003 (Crítico con ahorro por descuento) y P004 (Crítico sin descuento, ahorro
    0) comparten urgencia y se separan por ahorro; P002 (Atención) y P001 (Sin
    riesgo) cierran la cola.
    """
    return _dataframes(
        productos=[
            _producto("P001", stock_actual=500.0),
            _producto("P002", stock_actual=100.0),
            _producto("P003", stock_actual=0.0),
            _producto("P004", stock_actual=0.0),
        ],
        proveedores=[_proveedor("PR_DESCUENTO"), _proveedor("PR_SIN_DESCUENTO")],
        relaciones=[
            _relacion(
                "P003",
                "PR_DESCUENTO",
                precio=12.0,
                lead_time=15,
                umbral=500.0,
                descuento=5.0,
            ),
            _relacion("P003", "PR_SIN_DESCUENTO", precio=15.0, lead_time=15),
            _relacion("P004", "PR_SIN_DESCUENTO", precio=15.0, lead_time=15),
            _relacion("P002", "PR_SIN_DESCUENTO", precio=15.0, lead_time=20),
            _relacion("P001", "PR_SIN_DESCUENTO", precio=15.0, lead_time=20),
        ],
        historial=(
            _historial("P001", [50.0] * 6)
            + _historial("P002", [0.0, 500.0, 0.0, 500.0, 0.0, 500.0])
            + _historial("P003", [300.0] * 6)
            + _historial("P004", [300.0] * 6)
        ),
    )


def test_ordena_por_urgencia_luego_por_ahorro_descendente():
    resultado = _calcular(_escenario_para_orden())

    assert resultado["producto_id"].tolist() == ["P003", "P004", "P002", "P001"]
    assert resultado["urgencia"].tolist() == [
        URGENCIA_CRITICO,
        URGENCIA_CRITICO,
        URGENCIA_ATENCION,
        URGENCIA_SIN_RIESGO,
    ]
    ahorros = resultado["ahorro_neto_estimado"].tolist()
    assert ahorros[0] > 0.0
    # Dentro de la misma urgencia, el ahorro va de mayor a menor.
    assert ahorros[0] > ahorros[1] == 0.0


def test_con_urgencia_y_ahorro_iguales_desempata_por_producto_id_ascendente():
    entrada = _dataframes(
        productos=[
            _producto("P002", stock_actual=0.0),
            _producto("P001", stock_actual=0.0),
        ],
        proveedores=[_proveedor("PR1")],
        relaciones=[_relacion("P002", "PR1"), _relacion("P001", "PR1")],
        historial=_historial("P002", [300.0] * 6) + _historial("P001", [300.0] * 6),
    )

    resultado = _calcular(entrada)

    assert resultado["producto_id"].tolist() == ["P001", "P002"]
    assert resultado["urgencia"].tolist() == [URGENCIA_CRITICO, URGENCIA_CRITICO]
    assert resultado["ahorro_neto_estimado"].tolist() == [0.0, 0.0]


# ------------------------------------------------------- pureza y validación


def test_no_modifica_los_dataframes_de_entrada():
    entrada = _escenario_tres_productos()
    copias = tuple(marco.copy(deep=True) for marco in entrada)

    _calcular(entrada)

    for original, copia in zip(entrada, copias):
        pd.testing.assert_frame_equal(original, copia)


@pytest.mark.parametrize(
    ("tabla", "indice", "columna"),
    [
        ("productos", 0, "costo_ordenar"),
        ("proveedores", 1, "cumplimiento_entrega_pct"),
        ("producto_proveedor", 2, "lead_time_dias"),
        ("historial_demanda", 3, "periodo"),
    ],
)
def test_falta_una_columna_requerida_lanza_value_error(
    tabla: str, indice: int, columna: str
):
    entrada = list(_escenario_simple())
    entrada[indice] = entrada[indice].drop(columns=[columna])

    with pytest.raises(ValueError, match=tabla):
        _calcular(tuple(entrada))

    with pytest.raises(ValueError, match=columna):
        _calcular(tuple(entrada))


def test_costo_de_mantener_cero_propaga_el_value_error_del_motor():
    # H = costo_unitario * costo_mantener_pct_anual / 100 = 0: el EOQ no está
    # definido y el módulo del motor falla. El orquestador no lo captura.
    entrada = _escenario_simple(costo_mantener_pct_anual=0.0)

    with pytest.raises(ValueError, match="calcular_eoq_rop"):
        _calcular(entrada)


def test_periodos_por_año_dias_por_periodo_y_margen_llegan_al_motor():
    resultado = _calcular(
        _escenario_simple(),
        periodos_por_año=52,
        dias_por_periodo=7,
        margen_seguridad_pct=0.10,
    )
    fila = resultado.iloc[0]

    assert fila["cantidad_eoq"] == pytest.approx(
        np.sqrt(2.0 * 300.0 * 52.0 * 50.0 / 2.0)
    )
    assert fila["stock_seguridad"] == pytest.approx((300.0 / 7.0) * 15.0 * 0.10)
    assert fila["punto_reorden"] == pytest.approx((300.0 / 7.0) * 15.0 * 1.10)


def test_el_ahorro_usa_el_mismo_periodos_por_año_que_el_eoq():
    # El costo extra de mantener se prorratea con el mismo factor con el que se
    # anualizó la demanda del EOQ: si el orquestador no pasara el mismo
    # periodos_por_año a los dos módulos, el prorrateo no cuadraría con el EOQ.
    con_doce = _calcular(_escenario_simple(umbral=500.0, descuento=5.0))
    con_seis = _calcular(
        _escenario_simple(umbral=500.0, descuento=5.0), periodos_por_año=6
    )

    eoq_doce = np.sqrt(2.0 * 300.0 * 12.0 * 50.0 / 2.0)
    eoq_seis = np.sqrt(2.0 * 300.0 * 6.0 * 50.0 / 2.0)

    assert con_doce.loc[0, "cantidad_recomendada"] == pytest.approx(500.0)
    assert con_seis.loc[0, "cantidad_recomendada"] == pytest.approx(500.0)
    assert con_doce.loc[0, "costo_extra_mantener"] == pytest.approx(
        (500.0 - eoq_doce) * 10.0 * 0.20 / 12.0
    )
    assert con_seis.loc[0, "costo_extra_mantener"] == pytest.approx(
        (500.0 - eoq_seis) * 10.0 * 0.20 / 6.0
    )


# ------------------------------------------------- parámetros de configuración


def _parametros_custom(**cambios: float) -> dict[str, float]:
    """Los defaults del sistema con los cambios indicados.

    Devuelve un dict nuevo: los tests no mutan ``PARAMETROS_DEFAULT``.
    """
    return {**PARAMETROS_DEFAULT, **cambios}


def test_parametros_va_despues_de_historial_demanda_y_antes_de_eoq_rop():
    """El orden de la firma no rompe las llamadas posicionales existentes.

    ``parametros`` es el quinto argumento, no el último: los tres parámetros de
    eoq_rop (que no se configuran desde la tabla) mantienen su posición y una
    llamada posicional con las cuatro tablas sigue funcionando.
    """
    parametros_firma = list(inspect.signature(calcular_recomendaciones).parameters)

    assert parametros_firma == [
        "productos",
        "proveedores",
        "producto_proveedor",
        "historial_demanda",
        "parametros",
        "periodos_por_año",
        "dias_por_periodo",
        "margen_seguridad_pct",
    ]
    assert (
        inspect.signature(calcular_recomendaciones).parameters["parametros"].default
        is None
    )


def test_parametros_custom_cambian_los_cortes_de_abc():
    entrada = _escenario_tres_productos()

    por_defecto = _calcular(entrada).set_index("producto_id")
    con_corte_en_50 = _calcular(
        entrada, parametros=_parametros_custom(abc_clase_a_pct=50.0)
    ).set_index("producto_id")

    # Valor económico del escenario: P002 = 30000 (60.6 % del total), P001 =
    # 18000 (96.97 % acumulado) y P003 = 1500 (100 % acumulado). Con el corte por
    # defecto (80 %) P002 es 'A'; con 50 % su acumulado lo deja en la banda B.
    assert por_defecto.loc["P002", "clase_abc"] == "A"
    assert con_corte_en_50.loc["P002", "clase_abc"] == "B"
    # El corte de la clase B no se movió: P001 y P003 siguen en 'C'.
    assert por_defecto.loc["P001", "clase_abc"] == "C"
    assert con_corte_en_50.loc["P001", "clase_abc"] == "C"
    assert con_corte_en_50.loc["P003", "clase_abc"] == "C"


def test_parametros_custom_del_umbral_de_ahorro_marcan_mas_productos():
    entrada = _escenario_tres_productos()

    por_defecto = _calcular(entrada)
    con_umbral_cero = _calcular(
        entrada, parametros=_parametros_custom(ahorro_neto_min_pct=0.0)
    )

    # Por defecto solo P001 (descuento del 5 %) supera el 3 % del pedido.
    assert (por_defecto["estado_ahorro"] == "Ahorro detectado").sum() == 1
    # Con el umbral en 0 los tres quedan "Ahorro detectado": los productos sin
    # descuento tienen ahorro_neto = 0, que alcanza el umbral.
    assert (con_umbral_cero["estado_ahorro"] == "Ahorro detectado").all()
    # Lo que cambió es la decisión, no el cálculo del ahorro.
    pd.testing.assert_series_equal(
        con_umbral_cero["ahorro_neto_estimado"],
        por_defecto["ahorro_neto_estimado"],
    )


def test_parametros_none_usa_los_defaults_del_sistema():
    entrada = _escenario_tres_productos()

    sin_pasar = _calcular(entrada)
    con_none = _calcular(entrada, parametros=None)
    con_los_defaults = _calcular(entrada, parametros=dict(PARAMETROS_DEFAULT))

    # None y el dict de defaults dan exactamente el mismo resultado que omitir el
    # parámetro: los tests anteriores no cambiaron de comportamiento.
    pd.testing.assert_frame_equal(con_none, sin_pasar)
    pd.testing.assert_frame_equal(con_los_defaults, sin_pasar)


def test_la_ventana_de_demanda_se_convierte_a_int_aunque_llegue_como_float():
    # La tabla de configuración devuelve todos los valores como float (6.0), así
    # que sin el cast a int() estimar_demanda lanzaría ValueError por 'ventana'.
    entrada = _dataframes(
        productos=[_producto("P001", stock_actual=0.0)],
        proveedores=[_proveedor("PR1")],
        relaciones=[_relacion("P001", "PR1")],
        historial=_historial("P001", [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]),
    )

    con_ventana_dos = _calcular(
        entrada, parametros=_parametros_custom(demanda_ventana_default=2.0)
    )
    con_ventana_seis = _calcular(
        entrada, parametros=_parametros_custom(demanda_ventana_default=6.0)
    )

    # Con ventana 2 se promedian los dos últimos periodos (500 y 600) y con
    # ventana 6, los seis: el parámetro entra en el promedio como int.
    assert con_ventana_dos.loc[0, "demanda_estimada"] == pytest.approx(550.0)
    assert con_ventana_seis.loc[0, "demanda_estimada"] == pytest.approx(350.0)


def test_parametros_custom_del_cv_cambian_la_clase_xyz():
    entrada = _escenario_tres_productos()

    por_defecto = _calcular(entrada).set_index("producto_id")
    con_cortes_altos = _calcular(
        entrada,
        parametros=_parametros_custom(cv_confianza_alta=0.0, cv_confianza_media=2.0),
    ).set_index("producto_id")

    # P002 tiene CV ~ 1.095: es 'Z' con el corte Y por defecto (1.0) y pasa a 'Y'
    # cuando el corte sube a 2.0. P001 (CV 0) sigue siendo 'X'.
    assert por_defecto.loc["P002", "clase_xyz"] == "Z"
    assert con_cortes_altos.loc["P002", "clase_xyz"] == "Y"
    assert con_cortes_altos.loc["P001", "clase_xyz"] == "X"


def test_los_cortes_de_score_llegan_al_modulo_de_proveedores(monkeypatch):
    """Los cortes de score se propagan aunque no cambien la recomendación.

    El 'estado' del proveedor es lo único que depende de los cortes y no viaja a
    la salida, así que la propagación se comprueba con un espía sobre la función
    del motor que el orquestador tiene importada.
    """
    umbrales_usados: list[tuple[float, float]] = []

    def espia(datos, *, umbral_confiable, umbral_riesgoso):
        umbrales_usados.append((umbral_confiable, umbral_riesgoso))
        return calcular_score_proveedor(
            datos,
            umbral_confiable=umbral_confiable,
            umbral_riesgoso=umbral_riesgoso,
        )

    monkeypatch.setattr("src.recomendador.calcular_score_proveedor", espia)

    resultado = _calcular(
        _escenario_tres_productos(),
        parametros=_parametros_custom(
            score_proveedor_confiable=70.0, score_proveedor_riesgoso=50.0
        ),
    )

    assert umbrales_usados == [(70.0, 50.0)]
    # El score no depende de los cortes: la selección de proveedor no cambia.
    assert resultado.set_index("producto_id").loc["P001", "proveedor_id"] == "PR1"


# --------------------------------------- generar_recomendaciones (cliente falso)


class _RespuestaFalsa:
    """Respuesta mínima de PostgREST: solo el atributo ``data``."""

    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _TablaFalsa:
    """Constructor de consultas mínimo: ``select(...).execute()``."""

    def __init__(self, cliente: "_ClienteSupabaseFalso", nombre: str) -> None:
        self._cliente = cliente
        self._nombre = nombre

    def select(self, columnas: str) -> "_TablaFalsa":
        self._cliente.consultas.append((self._nombre, columnas))
        return self

    def execute(self) -> _RespuestaFalsa:
        return _RespuestaFalsa(self._cliente.datos[self._nombre])


class _ClienteSupabaseFalso:
    """Cliente de Supabase en memoria: sirve cada tabla por nombre.

    Registra en ``consultas`` cada ``select`` que recibe, para poder afirmar qué
    tablas se leyeron y en qué orden.
    """

    def __init__(self, datos: dict[str, list[dict]]) -> None:
        self.datos = datos
        self.consultas: list[tuple[str, str]] = []

    def table(self, nombre: str) -> _TablaFalsa:
        return _TablaFalsa(self, nombre)


def _tablas_supabase(
    parametros: dict[str, float] | None = None,
) -> dict[str, list[dict]]:
    """Las cinco tablas tal como las devuelve PostgREST (``id`` y ``nombre``).

    Las cuatro tablas de negocio se derivan del escenario de tres productos, con
    los nombres de columna de la base (``id``, ``nombre``); la de configuración se
    arma en el formato vertical de ``parametros_configuracion``
    (``nombre_parametro | valor | descripcion``) con ``parametros`` o, si es None,
    con los defaults del sistema.
    """
    productos, proveedores, relaciones, historial = _escenario_tres_productos()
    valores: dict[str, float] = PARAMETROS_DEFAULT if parametros is None else parametros

    return {
        "productos": [
            {
                "id": fila["producto_id"],
                "nombre": fila["nombre"],
                "categoria": fila["categoria"],
                "costo_unitario": fila["costo_unitario"],
                "stock_actual": fila["stock_actual"],
                "costo_ordenar": fila["costo_ordenar"],
                "costo_mantener_pct_anual": fila["costo_mantener_pct_anual"],
            }
            for _, fila in productos.iterrows()
        ],
        "proveedores": [
            {
                "id": fila["proveedor_id"],
                "nombre": fila["proveedor_nombre"],
                "cumplimiento_entrega_pct": fila["cumplimiento_entrega_pct"],
                "tasa_defectos_pct": fila["tasa_defectos_pct"],
            }
            for _, fila in proveedores.iterrows()
        ],
        "producto_proveedor": relaciones.to_dict(orient="records"),
        "historial_demanda": historial.to_dict(orient="records"),
        "parametros_configuracion": [
            {"nombre_parametro": nombre, "valor": valor, "descripcion": None}
            for nombre, valor in valores.items()
        ],
    }


def test_generar_recomendaciones_carga_los_parametros_de_supabase_y_los_usa():
    # La tabla de configuración se sirve con un corte ABC distinto del default:
    # así se comprueba de una vez que cargar_parametros se llama y que su
    # resultado llega al motor.
    cliente = _ClienteSupabaseFalso(
        _tablas_supabase(_parametros_custom(abc_clase_a_pct=50.0))
    )

    resultado = generar_recomendaciones(cliente).set_index("producto_id")

    # Las cinco tablas, cada una completa y una sola vez, en este orden.
    assert cliente.consultas == [
        ("productos", "*"),
        ("proveedores", "*"),
        ("producto_proveedor", "*"),
        ("historial_demanda", "*"),
        ("parametros_configuracion", "*"),
    ]
    # El renombre de columnas de la base sigue funcionando...
    assert resultado.loc["P001", "proveedor_nombre"] == "Proveedor PR1"
    # ...y el corte leído de Supabase (50 %) es el que clasifica: P002 baja de
    # 'A' (con los defaults) a 'B', y P001 y P003 quedan en 'C'.
    assert resultado.loc["P002", "clase_abc"] == "B"
    assert resultado.loc["P001", "clase_abc"] == "C"
    assert resultado.loc["P003", "clase_abc"] == "C"


def test_generar_recomendaciones_propaga_el_value_error_de_los_parametros():
    # Tabla de configuración vacía: cargar_parametros no puede armar el dict y
    # falla; la excepción se propaga igual que la de las lecturas de datos.
    tablas = _tablas_supabase()
    tablas["parametros_configuracion"] = []
    cliente = _ClienteSupabaseFalso(tablas)

    with pytest.raises(ValueError, match="faltan 10 de los 10"):
        generar_recomendaciones(cliente)


def test_generar_recomendaciones_con_los_defaults_en_la_tabla_no_cambia_nada():
    """Con la configuración servida con los defaults, el resultado es el mismo que
    el de la función pura sin parámetros: la lectura no altera el cálculo."""
    cliente = _ClienteSupabaseFalso(_tablas_supabase())

    resultado = generar_recomendaciones(cliente)
    esperado = _calcular(_escenario_tres_productos())

    pd.testing.assert_frame_equal(resultado, esperado)

