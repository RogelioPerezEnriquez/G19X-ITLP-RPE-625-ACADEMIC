"""Tests unitarios de EOQ, stock de seguridad y punto de reorden (motor OR).

Solo pruebas de la función pura ``src.motor.eoq_rop.calcular_eoq_rop``: no se
toca red, base de datos ni archivos.
"""

import numpy as np
import pandas as pd
import pytest

from src.motor.eoq_rop import (
    DIAS_POR_PERIODO_DEFAULT,
    MARGEN_SEGURIDAD_PCT_DEFAULT,
    PERIODOS_POR_AÑO_DEFAULT,
    calcular_eoq_rop,
)


# ---------------------------------------------------------------- utilidades


def _productos(
    producto_id: list,
    costo_unitario: list,
    costo_ordenar: list,
    costo_mantener_pct_anual: list,
    demanda_estimada: list,
    lead_time_dias: list,
) -> pd.DataFrame:
    """Construye el DataFrame de entrada mínimo que espera el motor."""
    return pd.DataFrame(
        {
            "producto_id": producto_id,
            "costo_unitario": costo_unitario,
            "costo_ordenar": costo_ordenar,
            "costo_mantener_pct_anual": costo_mantener_pct_anual,
            "demanda_estimada": demanda_estimada,
            "lead_time_dias": lead_time_dias,
        }
    )


def _p001(**cambios: object) -> pd.DataFrame:
    """DataFrame de una fila con los valores del ejemplo P001 del enunciado.

    Cada valor se puede sobrescribir por nombre para construir los casos borde:
    ``_p001(costo_unitario=0.0)``, ``_p001(lead_time_dias=0)``, etc.
    """
    base: dict = {
        "producto_id": "P001",
        "costo_unitario": 25.0,
        "costo_ordenar": 50.0,
        "costo_mantener_pct_anual": 20.0,
        "demanda_estimada": 100.0,
        "lead_time_dias": 7,
    }
    base.update(cambios)
    return _productos(**{nombre: [valor] for nombre, valor in base.items()})


def _valor(resultado: pd.DataFrame, producto_id: str, columna: str) -> float:
    """Valor de ``columna`` para el producto indicado, sin depender del orden."""
    return float(resultado.set_index("producto_id").loc[producto_id, columna])


def _columnas_numericas(resultado: pd.DataFrame) -> np.ndarray:
    """Las tres columnas de salida numéricas, como matriz de float64."""
    return resultado[["cantidad_eoq", "stock_seguridad", "punto_reorden"]].to_numpy(
        dtype="float64"
    )


# ------------------------------------------------------------ caso principal


def test_los_defaults_son_las_constantes_del_modulo():
    """Sin argumentos se usan las constantes del módulo, que valen 12/30/0.20."""
    assert PERIODOS_POR_AÑO_DEFAULT == 12
    assert DIAS_POR_PERIODO_DEFAULT == 30
    assert MARGEN_SEGURIDAD_PCT_DEFAULT == 0.20

    pd.testing.assert_frame_equal(
        calcular_eoq_rop(_p001()),
        calcular_eoq_rop(
            _p001(),
            periodos_por_año=12,
            dias_por_periodo=30,
            margen_seguridad_pct=0.20,
        ),
    )


def test_caso_normal_del_ejemplo_p001():
    """P001: EOQ = sqrt(24000) ≈ 154.9193, SS ≈ 4.6667 y ROP = 28.0.

    H = 25.00 * (20 / 100) = 5.00 por unidad y año
    D = 100 * 12 = 1200 unidades por año
    demanda_diaria = 100 / 30 ≈ 3.3333
    """
    resultado = calcular_eoq_rop(_p001())

    assert resultado["producto_id"].tolist() == ["P001"]
    assert list(resultado.columns) == [
        "producto_id",
        "cantidad_eoq",
        "stock_seguridad",
        "punto_reorden",
    ]

    assert _valor(resultado, "P001", "cantidad_eoq") == pytest.approx(
        np.sqrt(2 * 1200.0 * 50.0 / 5.0)
    )
    assert _valor(resultado, "P001", "cantidad_eoq") == pytest.approx(
        np.sqrt(24_000.0)
    )
    assert _valor(resultado, "P001", "cantidad_eoq") == pytest.approx(
        154.9193, abs=1e-4
    )

    assert _valor(resultado, "P001", "stock_seguridad") == pytest.approx(
        100.0 / 30 * 7 * 0.20
    )
    assert _valor(resultado, "P001", "stock_seguridad") == pytest.approx(
        4.6667, abs=1e-4
    )
    assert _valor(resultado, "P001", "punto_reorden") == pytest.approx(28.0)


def test_multiples_productos_se_calculan_por_separado_y_ordenados():
    """Tres productos con valores distintos, en orden de entrada inverso."""
    datos = _productos(
        producto_id=["P003", "P002", "P001"],
        costo_unitario=[10.0, 18.0, 25.0],
        costo_ordenar=[20.0, 45.0, 50.0],
        costo_mantener_pct_anual=[10.0, 20.0, 20.0],
        demanda_estimada=[40.0, 80.0, 100.0],
        lead_time_dias=[3, 5, 7],
    )

    resultado = calcular_eoq_rop(datos)

    assert resultado["producto_id"].tolist() == ["P001", "P002", "P003"]

    # P002: H = 18 * 0.20 = 3.6; P003: H = 10 * 0.10 = 1.0
    assert _valor(resultado, "P001", "cantidad_eoq") == pytest.approx(
        np.sqrt(24_000.0)
    )
    assert _valor(resultado, "P002", "cantidad_eoq") == pytest.approx(
        np.sqrt(2 * 80.0 * 12 * 45.0 / 3.6)
    )
    assert _valor(resultado, "P003", "cantidad_eoq") == pytest.approx(
        np.sqrt(2 * 40.0 * 12 * 20.0 / 1.0)
    )

    # ROP = demanda_diaria * lead_time * (1 + margen)
    assert _valor(resultado, "P001", "punto_reorden") == pytest.approx(28.0)
    assert _valor(resultado, "P002", "punto_reorden") == pytest.approx(
        80.0 / 30 * 5 * 1.20
    )
    assert _valor(resultado, "P003", "punto_reorden") == pytest.approx(
        40.0 / 30 * 3 * 1.20
    )


# ------------------------------------------------------- H no positivo (EOQ)


def test_costo_mantener_pct_anual_cero_lanza_value_error_nombrando_el_producto():
    """H = 0 en P002 (pct = 0): el mensaje señala al producto culpable."""
    datos = _productos(
        producto_id=["P001", "P002"],
        costo_unitario=[25.0, 18.0],
        costo_ordenar=[50.0, 45.0],
        costo_mantener_pct_anual=[20.0, 0.0],
        demanda_estimada=[100.0, 80.0],
        lead_time_dias=[7, 5],
    )

    with pytest.raises(ValueError, match="P002") as excepcion:
        calcular_eoq_rop(datos)

    assert "H" in str(excepcion.value)
    assert "P001" not in str(excepcion.value)


def test_costo_unitario_cero_lanza_value_error():
    """H = 0 * (20 / 100) = 0: un producto sin costo tampoco tiene EOQ."""
    with pytest.raises(ValueError, match="P001"):
        calcular_eoq_rop(_p001(costo_unitario=0.0))


# ------------------------------------------------------------ casos borde


def test_lead_time_cero_da_ss_y_rop_cero():
    """Sin tiempo de entrega no hay consumo que cubrir."""
    resultado = calcular_eoq_rop(_p001(lead_time_dias=0))

    assert _valor(resultado, "P001", "stock_seguridad") == 0.0
    assert _valor(resultado, "P001", "punto_reorden") == 0.0
    # El EOQ no depende del lead time.
    assert _valor(resultado, "P001", "cantidad_eoq") == pytest.approx(
        np.sqrt(24_000.0)
    )


def test_demanda_estimada_cero_da_eoq_ss_y_rop_cero():
    """D = 0 y consumo nulo: los tres valores son 0, no nan ni inf."""
    resultado = calcular_eoq_rop(_p001(demanda_estimada=0.0))

    assert _valor(resultado, "P001", "cantidad_eoq") == 0.0
    assert _valor(resultado, "P001", "stock_seguridad") == 0.0
    assert _valor(resultado, "P001", "punto_reorden") == 0.0
    assert not bool(resultado.isna().to_numpy().any())


def test_margen_cero_da_ss_cero_y_rop_sin_margen():
    """margen 0 es válido (y se acepta como int): SS = 0 y ROP = consumo base."""
    resultado = calcular_eoq_rop(_p001(), margen_seguridad_pct=0)

    assert _valor(resultado, "P001", "stock_seguridad") == 0.0
    assert _valor(resultado, "P001", "punto_reorden") == pytest.approx(
        100.0 / 30 * 7
    )
    assert _valor(resultado, "P001", "punto_reorden") == pytest.approx(
        23.3333, abs=1e-4
    )


def test_margen_0_5_duplica_el_ss_del_margen_0_25():
    """El SS es proporcional al margen; el ROP solo en la parte del colchón."""
    con_025 = calcular_eoq_rop(_p001(), margen_seguridad_pct=0.25)
    con_050 = calcular_eoq_rop(_p001(), margen_seguridad_pct=0.50)

    ss_025 = _valor(con_025, "P001", "stock_seguridad")
    ss_050 = _valor(con_050, "P001", "stock_seguridad")

    assert ss_025 == pytest.approx(100.0 / 30 * 7 * 0.25)
    assert ss_050 == pytest.approx(2 * ss_025)
    assert _valor(con_050, "P001", "punto_reorden") == pytest.approx(
        100.0 / 30 * 7 * 1.5
    )


def test_periodos_por_año_52_escala_el_eoq():
    """Con 52 periodos por año, D y el EOQ escalan con sqrt(52 / 12)."""
    mensual = calcular_eoq_rop(_p001())
    semanal = calcular_eoq_rop(_p001(), periodos_por_año=52)

    assert _valor(semanal, "P001", "cantidad_eoq") == pytest.approx(
        np.sqrt(2 * 100.0 * 52 * 50.0 / 5.0)
    )
    assert _valor(semanal, "P001", "cantidad_eoq") == pytest.approx(
        _valor(mensual, "P001", "cantidad_eoq") * np.sqrt(52 / 12)
    )
    # SS y ROP no dependen de periodos_por_año.
    assert _valor(semanal, "P001", "stock_seguridad") == pytest.approx(
        _valor(mensual, "P001", "stock_seguridad")
    )
    assert _valor(semanal, "P001", "punto_reorden") == pytest.approx(
        _valor(mensual, "P001", "punto_reorden")
    )


def test_dias_por_periodo_7_escala_ss_y_rop():
    """Con 7 días por periodo la demanda diaria (y el SS) escala con 30 / 7."""
    mensual = calcular_eoq_rop(_p001())
    semanal = calcular_eoq_rop(_p001(), dias_por_periodo=7)

    factor = 30.0 / 7.0
    assert _valor(semanal, "P001", "stock_seguridad") == pytest.approx(
        100.0 / 7 * 7 * 0.20
    )
    assert _valor(semanal, "P001", "stock_seguridad") == pytest.approx(
        _valor(mensual, "P001", "stock_seguridad") * factor
    )
    assert _valor(semanal, "P001", "punto_reorden") == pytest.approx(
        _valor(mensual, "P001", "punto_reorden") * factor
    )
    # El EOQ no depende de dias_por_periodo.
    assert _valor(semanal, "P001", "cantidad_eoq") == pytest.approx(
        _valor(mensual, "P001", "cantidad_eoq")
    )


# ------------------------------------------------------ parámetros inválidos


@pytest.mark.parametrize("valor", [0, -3, 12.5, True])
def test_periodos_por_año_invalido_lanza_value_error(valor):
    """0, negativo, no entero y bool no son periodos por año válidos."""
    with pytest.raises(ValueError, match="periodos_por_año"):
        calcular_eoq_rop(_p001(), periodos_por_año=valor)


@pytest.mark.parametrize("valor", [0, -7, 30.5, False])
def test_dias_por_periodo_invalido_lanza_value_error(valor):
    """0, negativo, no entero y bool no son días por periodo válidos."""
    with pytest.raises(ValueError, match="dias_por_periodo"):
        calcular_eoq_rop(_p001(), dias_por_periodo=valor)


@pytest.mark.parametrize("valor", [-0.01, "0.2", None, True])
def test_margen_seguridad_invalido_lanza_value_error(valor):
    """Negativo, no numérico y bool no son márgenes de seguridad válidos."""
    with pytest.raises(ValueError, match="margen_seguridad_pct"):
        calcular_eoq_rop(_p001(), margen_seguridad_pct=valor)


# ------------------------------------------- vacío, columnas y orden de fallos


def test_dataframe_vacio_con_columnas_devuelve_vacio_sin_error():
    """Sin filas no hay nada que calcular: se devuelve la salida vacía."""
    vacio = pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "costo_unitario": pd.Series(dtype="float64"),
            "costo_ordenar": pd.Series(dtype="float64"),
            "costo_mantener_pct_anual": pd.Series(dtype="float64"),
            "demanda_estimada": pd.Series(dtype="float64"),
            "lead_time_dias": pd.Series(dtype="int64"),
        }
    )

    resultado = calcular_eoq_rop(vacio)

    assert resultado.empty
    assert list(resultado.columns) == [
        "producto_id",
        "cantidad_eoq",
        "stock_seguridad",
        "punto_reorden",
    ]
    assert resultado["producto_id"].dtype == object
    assert resultado["cantidad_eoq"].dtype == "float64"
    assert resultado["stock_seguridad"].dtype == "float64"
    assert resultado["punto_reorden"].dtype == "float64"
    assert resultado.index.tolist() == []


def test_orden_de_validacion_parametros_columnas_y_vacio():
    """Escalares -> columnas -> vacío, tenga o no filas la entrada."""
    # 1) Parámetro inválido y DataFrame sin columnas: falla el parámetro.
    with pytest.raises(ValueError, match="periodos_por_año"):
        calcular_eoq_rop(pd.DataFrame(), periodos_por_año=0)

    # 2) DataFrame vacío sin columnas: fallan las columnas, no se devuelve vacío.
    with pytest.raises(ValueError) as excepcion:
        calcular_eoq_rop(pd.DataFrame())
    assert "producto_id" in str(excepcion.value)
    assert "lead_time_dias" in str(excepcion.value)

    # 3) DataFrame con filas y sin una columna requerida: también falla.
    with pytest.raises(ValueError, match="demanda_estimada"):
        calcular_eoq_rop(_p001().drop(columns=["demanda_estimada"]))


# ------------------------------------------- contrato de salida y pureza


def test_la_salida_tiene_las_columnas_los_dtypes_y_el_indice_esperados():
    resultado = calcular_eoq_rop(_p001())

    assert list(resultado.columns) == [
        "producto_id",
        "cantidad_eoq",
        "stock_seguridad",
        "punto_reorden",
    ]
    assert resultado["producto_id"].dtype == object
    assert resultado["cantidad_eoq"].dtype == "float64"
    assert resultado["stock_seguridad"].dtype == "float64"
    assert resultado["punto_reorden"].dtype == "float64"
    assert resultado.index.tolist() == [0]


def test_no_modifica_el_dataframe_de_entrada():
    datos = _p001()
    copia = datos.copy(deep=True)

    calcular_eoq_rop(datos)

    pd.testing.assert_frame_equal(datos, copia)
    assert "cantidad_eoq" not in datos.columns


def test_el_orden_de_las_filas_de_entrada_no_altera_el_resultado():
    """La salida depende de los datos, no del orden en que llegaron."""
    datos = _productos(
        producto_id=["P003", "P002", "P001"],
        costo_unitario=[10.0, 18.0, 25.0],
        costo_ordenar=[20.0, 45.0, 50.0],
        costo_mantener_pct_anual=[10.0, 20.0, 20.0],
        demanda_estimada=[40.0, 80.0, 100.0],
        lead_time_dias=[3, 5, 7],
    )
    desordenado = datos.iloc[[1, 2, 0]]

    pd.testing.assert_frame_equal(
        calcular_eoq_rop(datos),
        calcular_eoq_rop(desordenado),
    )


# ------------------------------------------------------------------- escala


def test_valores_muy_grandes_no_rompen_el_calculo():
    datos = _productos(
        producto_id=["P001"],
        costo_unitario=[1e12],
        costo_ordenar=[1e12],
        costo_mantener_pct_anual=[20.0],
        demanda_estimada=[1e12],
        lead_time_dias=[14],
    )

    resultado = calcular_eoq_rop(datos)

    assert _valor(resultado, "P001", "cantidad_eoq") == pytest.approx(
        np.sqrt(2 * (1e12 * 12) * 1e12 / (1e12 * 0.20)), rel=1e-12
    )
    assert _valor(resultado, "P001", "stock_seguridad") == pytest.approx(
        1e12 / 30 * 14 * 0.20, rel=1e-12
    )
    assert np.isfinite(_columnas_numericas(resultado)).all()


def test_valores_muy_pequenos_no_rompen_el_calculo():
    """H = 1e-13 sigue siendo positivo: el EOQ está definido y es finito."""
    datos = _productos(
        producto_id=["P001"],
        costo_unitario=[1e-9],
        costo_ordenar=[1e-9],
        costo_mantener_pct_anual=[0.01],
        demanda_estimada=[1e-9],
        lead_time_dias=[1],
    )

    resultado = calcular_eoq_rop(datos)

    assert _valor(resultado, "P001", "cantidad_eoq") == pytest.approx(
        np.sqrt(2 * (1e-9 * 12) * 1e-9 / (1e-9 * 0.0001)), rel=1e-12
    )
    assert _valor(resultado, "P001", "cantidad_eoq") > 0.0
    assert _valor(resultado, "P001", "stock_seguridad") == pytest.approx(
        1e-9 / 30 * 0.20, rel=1e-12
    )
    assert np.isfinite(_columnas_numericas(resultado)).all()

