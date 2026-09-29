"""Tests unitarios de la clasificación ABC del motor OR.

Solo pruebas de la función pura ``src.motor.abc.clasificar_abc``: no se toca
red, base de datos ni archivos.

La última sección cubre los umbrales configurables (fase 4): las clases se
calculan con los cortes que recibe la función y sus valores por defecto se leen
de :data:`src.config.PARAMETROS_DEFAULT`.
"""

import inspect

import pandas as pd
import pytest

from src.config import PARAMETROS_DEFAULT
from src.motor.abc import clasificar_abc


# ---------------------------------------------------------------- utilidades


def _productos(
    producto_id: list,
    costo_unitario: list,
    demanda_total: list,
    index: list | None = None,
) -> pd.DataFrame:
    """Construye el DataFrame de entrada mínimo que espera el motor."""
    return pd.DataFrame(
        {
            "producto_id": producto_id,
            "costo_unitario": costo_unitario,
            "demanda_total": demanda_total,
        },
        index=index,
    )


def _por_valores(valores: list[float], ids: list | None = None) -> pd.DataFrame:
    """DataFrame con costo 1.0 y demanda igual al valor económico deseado."""
    ids = ids if ids is not None else [f"P{i + 1}" for i in range(len(valores))]
    return _productos(ids, [1.0] * len(valores), list(valores))


def _mapa_clases(resultado: pd.DataFrame) -> dict:
    """Devuelve {producto_id: clase_abc}, sin depender del orden de las filas."""
    return dict(zip(resultado["producto_id"], resultado["clase_abc"]))


# ------------------------------------------------------------ caso principal


def test_caso_normal_del_ejemplo():
    """Valores 100, 80, 15, 5 (total 200) -> acumulados 50, 90, 97.5, 100."""
    resultado = clasificar_abc(_por_valores([100.0, 80.0, 15.0, 5.0]))

    assert resultado["clase_abc"].tolist() == ["A", "B", "C", "C"]


def test_valor_economico_es_costo_unitario_por_demanda_total():
    """Se clasifica por costo * demanda, no por la demanda sola."""
    # P1: 10 * 1 = 10 ; P2: 1 * 100 = 100 (total 110) -> P2 concentra el 90.9 %
    resultado = clasificar_abc(_productos(["P1", "P2"], [10.0, 1.0], [1.0, 100.0]))

    assert _mapa_clases(resultado) == {"P1": "C", "P2": "B"}


def test_acepta_columnas_de_tipo_entero():
    resultado = clasificar_abc(_productos(["P1", "P2"], [10, 1], [1, 100]))

    assert _mapa_clases(resultado) == {"P1": "C", "P2": "B"}


def test_las_etiquetas_son_solo_a_b_o_c():
    resultado = clasificar_abc(_por_valores([50.0, 30.0, 15.0, 5.0]))

    assert set(resultado["clase_abc"]) <= {"A", "B", "C"}


# ------------------------------------------------------------- caso borde n=1


def test_un_solo_producto_es_clase_a():
    resultado = clasificar_abc(_productos(["P1"], [3.5], [120.0]))

    assert resultado["clase_abc"].tolist() == ["A"]


def test_un_solo_producto_con_valor_cero_es_clase_c():
    """La regla de valor total 0 tiene prioridad sobre el caso de un producto."""
    resultado = clasificar_abc(_productos(["P1"], [0.0], [0.0]))

    assert resultado["clase_abc"].tolist() == ["C"]


# ------------------------------------------------------------------ vacío


def test_dataframe_vacio_devuelve_copia_vacia_sin_error():
    vacio = pd.DataFrame(
        {
            "producto_id": pd.Series(dtype="object"),
            "costo_unitario": pd.Series(dtype="float64"),
            "demanda_total": pd.Series(dtype="float64"),
        }
    )

    resultado = clasificar_abc(vacio)

    assert resultado.empty
    assert list(resultado.columns) == [
        "producto_id",
        "costo_unitario",
        "demanda_total",
        "clase_abc",
    ]
    assert len(resultado["clase_abc"]) == 0
    assert pd.api.types.is_string_dtype(resultado["clase_abc"])


def test_dataframe_vacio_sin_columnas_lanza_value_error():
    """Sin filas pero sin columnas también falla: la validación es estricta."""
    with pytest.raises(ValueError, match="faltan") as excepcion:
        clasificar_abc(pd.DataFrame())

    # El mensaje nombra cada columna requerida que falta.
    mensaje = str(excepcion.value)
    assert "producto_id" in mensaje
    assert "costo_unitario" in mensaje
    assert "demanda_total" in mensaje


def test_dataframe_vacio_no_se_modifica_a_si_mismo():
    vacio = pd.DataFrame(
        {
            "producto_id": pd.Series(dtype="object"),
            "costo_unitario": pd.Series(dtype="float64"),
            "demanda_total": pd.Series(dtype="float64"),
        }
    )
    copia = vacio.copy(deep=True)

    clasificar_abc(vacio)

    pd.testing.assert_frame_equal(vacio, copia)


# --------------------------------------------------------- valor total cero


@pytest.mark.parametrize(
    ("costo_unitario", "demanda_total"),
    [
        ([0.0, 12.5, 7.0], [0.0, 0.0, 0.0]),  # demanda cero
        ([0.0, 0.0, 0.0], [34.0, 12.0, 9.0]),  # costo cero
    ],
)
def test_todos_los_productos_valen_cero_son_clase_c(costo_unitario, demanda_total):
    """No hay división por cero: todos quedan en la clase C."""
    resultado = clasificar_abc(
        _productos(["P1", "P2", "P3"], costo_unitario, demanda_total)
    )

    assert resultado["clase_abc"].tolist() == ["C", "C", "C"]


# ------------------------------------------------------- cortes exactos 80/95


@pytest.mark.parametrize(
    "valores",
    [
        [80.0, 20.0],
        [8.0, 2.0],
        [160.0, 40.0],
        [4.0, 1.0],
    ],
)
def test_acumulado_exactamente_80_es_clase_a(valores):
    resultado = clasificar_abc(_por_valores(valores))

    assert resultado["clase_abc"].tolist()[0] == "A"
    assert resultado["clase_abc"].tolist()[-1] == "C"


def test_acumulado_exactamente_80_en_catalogo_mixto():
    """Total 100: acumulados 80 (A), 90 (B), 95 (B), 100 (C)."""
    resultado = clasificar_abc(_por_valores([80.0, 10.0, 5.0, 5.0]))

    assert resultado["clase_abc"].tolist() == ["A", "B", "B", "C"]


@pytest.mark.parametrize(
    "valores",
    [
        [95.0, 5.0],
        [19.0, 1.0],
        [190.0, 10.0],
    ],
)
def test_acumulado_exactamente_95_es_clase_b(valores):
    resultado = clasificar_abc(_por_valores(valores))

    assert resultado["clase_abc"].tolist()[0] == "B"
    assert resultado["clase_abc"].tolist()[-1] == "C"


def test_acumulado_exactamente_95_en_catalogo_mixto():
    """Total 100: acumulados 90 (B), 95 (B, inclusivo), 100 (C)."""
    resultado = clasificar_abc(_por_valores([90.0, 5.0, 5.0]))

    assert resultado["clase_abc"].tolist() == ["B", "B", "C"]


# ------------------------------------------------------------------ empates


def test_empate_usa_producto_id_ascendente_de_forma_determinista():
    """Ante empate, el acumulado se resuelve por producto_id ascendente.

    Total 100: P1 = 60 (A). El empate de 20 entre P2 y P3 se ordena por
    producto_id ascendente, así que P2 acumula 80 (A) y P3 acumula 100 (C).
    """
    resultado = clasificar_abc(
        _productos(["P3", "P1", "P2"], [1.0] * 3, [20.0, 60.0, 20.0])
    )

    assert _mapa_clases(resultado) == {"P1": "A", "P2": "A", "P3": "C"}


def test_empate_da_el_mismo_resultado_con_otro_orden_de_filas():
    primera = clasificar_abc(
        _productos(["P3", "P1", "P2"], [1.0] * 3, [20.0, 60.0, 20.0])
    )
    segunda = clasificar_abc(
        _productos(["P1", "P2", "P3"], [1.0] * 3, [60.0, 20.0, 20.0], index=[5, 6, 7])
    )

    assert _mapa_clases(primera) == _mapa_clases(segunda)
    assert _mapa_clases(segunda) == {"P1": "A", "P2": "A", "P3": "C"}


# --------------------------------------------------- índice y orden original


def test_preserva_indice_y_orden_de_las_filas():
    productos = _productos(
        ["P3", "P1", "P2"], [1.0] * 3, [20.0, 60.0, 20.0], index=[9, 4, 7]
    )

    resultado = clasificar_abc(productos)

    assert resultado.index.tolist() == [9, 4, 7]
    assert resultado["producto_id"].tolist() == ["P3", "P1", "P2"]
    assert resultado["clase_abc"].tolist() == ["C", "A", "A"]
    assert _mapa_clases(resultado) == {"P1": "A", "P2": "A", "P3": "C"}


def test_cada_producto_id_recibe_la_clase_que_le_corresponde():
    """La clase sigue al producto, no a la posición de la fila."""
    resultado = clasificar_abc(
        _por_valores([100.0, 80.0, 15.0, 5.0], ids=["C4", "C1", "C3", "C2"])
    )

    assert _mapa_clases(resultado) == {"C1": "B", "C2": "C", "C3": "C", "C4": "A"}


def test_indice_con_etiquetas_repetidas_no_rompe_la_asignacion():
    productos = _productos(
        ["P3", "P1", "P2"], [1.0] * 3, [20.0, 60.0, 20.0], index=["x", "x", "y"]
    )

    resultado = clasificar_abc(productos)

    assert resultado.index.tolist() == ["x", "x", "y"]
    assert resultado["clase_abc"].tolist() == ["C", "A", "A"]


# ---------------------------------------------- pureza y validación de entrada


def test_no_modifica_el_dataframe_de_entrada():
    productos = _por_valores([100.0, 80.0, 15.0, 5.0])
    copia = productos.copy(deep=True)

    clasificar_abc(productos)

    pd.testing.assert_frame_equal(productos, copia)
    assert "clase_abc" not in productos.columns


def test_conserva_las_columnas_originales_y_agrega_clase_abc():
    resultado = clasificar_abc(_productos(["P1"], [1.0], [10.0]))

    assert list(resultado.columns) == [
        "producto_id",
        "costo_unitario",
        "demanda_total",
        "clase_abc",
    ]


def test_falta_una_columna_requerida_lanza_value_error():
    with pytest.raises(ValueError, match="producto_id"):
        clasificar_abc(pd.DataFrame({"costo_unitario": [1.0], "demanda_total": [1.0]}))


# ------------------------------------------- umbrales configurables (fase 4)


def test_los_defaults_de_los_umbrales_vienen_de_config():
    """Sin argumentos se usan los umbrales de PARAMETROS_DEFAULT (80 y 95)."""
    parametros = inspect.signature(clasificar_abc).parameters

    assert parametros["umbral_clase_a"].default == (
        PARAMETROS_DEFAULT["abc_clase_a_pct"]
    )
    assert parametros["umbral_clase_b"].default == (
        PARAMETROS_DEFAULT["abc_clase_b_pct"]
    )
    # Y los valores de config siguen siendo los históricos del módulo.
    assert PARAMETROS_DEFAULT["abc_clase_a_pct"] == 80.0
    assert PARAMETROS_DEFAULT["abc_clase_b_pct"] == 95.0


def test_los_defaults_dan_el_mismo_resultado_que_pasarlos_explicitos():
    """No pasar umbrales equivale a pasar 80.0 y 95.0: nada cambió por defecto."""
    catalogo = _por_valores([100.0, 80.0, 15.0, 5.0])

    pd.testing.assert_frame_equal(
        clasificar_abc(catalogo),
        clasificar_abc(catalogo, umbral_clase_a=80.0, umbral_clase_b=95.0),
    )


def test_umbrales_custom_70_90_mueven_los_dos_cortes():
    """Valores 75, 10, 8 y 7 (total 100) -> acumulados 75, 85, 93 y 100.

    Con los umbrales por defecto el resultado es A, B, B, C. Al estrechar las
    bandas a 70/90, el producto mayor deja de ser A (75 > 70) y el tercero deja
    de ser B (93 > 90), así que el resultado pasa a ser B, B, C, C.
    """
    catalogo = _por_valores([75.0, 10.0, 8.0, 7.0])

    assert clasificar_abc(catalogo)["clase_abc"].tolist() == ["A", "B", "B", "C"]

    custom = clasificar_abc(catalogo, umbral_clase_a=70.0, umbral_clase_b=90.0)

    assert custom["clase_abc"].tolist() == ["B", "B", "C", "C"]


def test_umbrales_custom_70_90_respetan_las_fronteras_exactas():
    """Acumulados exactos de 70 y de 90: 70 entra en A y 90 entra en B."""
    catalogo = _por_valores([70.0, 20.0, 10.0])

    resultado = clasificar_abc(catalogo, umbral_clase_a=70.0, umbral_clase_b=90.0)

    assert resultado["clase_abc"].tolist() == ["A", "B", "C"]


def test_umbral_100_en_los_dos_cortes_da_todo_clase_a():
    """Caso borde: con 100/100 ningún acumulado supera el corte de A.

    Valores 50, 30, 15 y 5 (total 100) -> acumulados 50, 80, 95 y 100, todos
    <= 100, así que los cuatro productos son clase A (incluido el último, cuyo
    acumulado es exactamente 100 %).
    """
    catalogo = _por_valores([50.0, 30.0, 15.0, 5.0])

    resultado = clasificar_abc(catalogo, umbral_clase_a=100.0, umbral_clase_b=100.0)

    assert resultado["clase_abc"].tolist() == ["A", "A", "A", "A"]


def test_umbral_clase_a_cero_deja_la_banda_a_vacia():
    """Caso borde: umbral_clase_a = 0 y umbral_clase_b = 100.

    La comparación es contra el porcentaje *acumulado*, así que con
    umbral_clase_a = 0 la banda A queda vacía: ningún acumulado positivo es
    <= 0. Con 40, 30, 20 y 10 (acumulados 40, 70, 90 y 100) los cuatro productos
    caen en B, porque el corte de B es 100 y ninguno lo supera.
    """
    catalogo = _por_valores([40.0, 30.0, 20.0, 10.0])

    resultado = clasificar_abc(catalogo, umbral_clase_a=0.0, umbral_clase_b=100.0)

    assert resultado["clase_abc"].tolist() == ["B", "B", "B", "B"]


def test_umbral_clase_a_igual_al_mayor_producto_deja_en_a_solo_al_primero():
    """Cómo dejar solo al producto de mayor valor en A: umbral_clase_a = 40.

    Valores 40, 30, 20 y 10 (total 100) -> acumulados 40, 70, 90 y 100: solo el
    primero entra en A (40 <= 40) y los tres restantes quedan en B (<= 100).
    """
    catalogo = _por_valores([40.0, 30.0, 20.0, 10.0])

    resultado = clasificar_abc(catalogo, umbral_clase_a=40.0, umbral_clase_b=100.0)

    assert resultado["clase_abc"].tolist() == ["A", "B", "B", "B"]
    assert resultado["clase_abc"].tolist().count("A") == 1

