"""Tests unitarios de la estimación de demanda del motor OR.

Solo pruebas de la función pura ``src.motor.demanda.estimar_demanda``: no se
toca red, base de datos ni archivos.

La última sección cubre la ventana configurable (fase 4): el tamaño de la
ventana es un parámetro de ``estimar_demanda`` y su valor por defecto se lee de
:data:`src.config.PARAMETROS_DEFAULT`.
"""

import inspect

import pandas as pd
import pytest

from src.config import PARAMETROS_DEFAULT
from src.motor.demanda import estimar_demanda


# ---------------------------------------------------------------- utilidades


def _historial(
    producto_id: list,
    periodo: list,
    cantidad_demandada: list,
) -> pd.DataFrame:
    """Construye el DataFrame de entrada mínimo que espera el motor."""
    return pd.DataFrame(
        {
            "producto_id": producto_id,
            "periodo": periodo,
            "cantidad_demandada": cantidad_demandada,
        }
    )


def _periodos(
    producto_id: str, cantidades: list, inicio: str = "2025-01-01"
) -> pd.DataFrame:
    """Historial de un solo producto, con un periodo mensual por cantidad."""
    return _historial(
        [producto_id] * len(cantidades),
        list(pd.date_range(start=inicio, periods=len(cantidades), freq="MS")),
        list(cantidades),
    )


def _apilados(por_producto: dict) -> pd.DataFrame:
    """Concatena varios productos {producto_id: [cantidades]}.

    Las filas de cada producto van en bloque, para que el orden de entrada sea
    distinto del orden de salida esperado (producto_id ascendente).
    """
    partes = [_periodos(pid, cantidades) for pid, cantidades in por_producto.items()]
    return pd.concat(partes, ignore_index=True)


def _demanda(resultado: pd.DataFrame, producto_id: str) -> float:
    """demanda_estimada del producto indicado, sin depender del orden."""
    return resultado.set_index("producto_id").loc[producto_id, "demanda_estimada"]


# ------------------------------------------------------------ caso principal


def test_caso_normal_del_ejemplo_con_ventana_6():
    """P001 del ejemplo: últimos 6 de 8 periodos = [98, 102, 110, 95, 108, 100]."""
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])

    resultado = estimar_demanda(historial, ventana=6)

    assert _demanda(resultado, "P001") == pytest.approx(613 / 6)
    assert _demanda(resultado, "P001") == pytest.approx(102.1667, abs=1e-4)
    assert resultado["demanda_estimada"].dtype == "float64"


def test_caso_normal_del_ejemplo_con_ventana_3():
    """P001 del ejemplo: los últimos 3 periodos son [95, 108, 100]."""
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])

    resultado = estimar_demanda(historial, ventana=3)

    assert _demanda(resultado, "P001") == pytest.approx(101.0)


def test_producto_con_menos_periodos_que_la_ventana_usa_todos():
    """P002 del ejemplo: 2 periodos con ventana=6 -> (50 + 80) / 2."""
    resultado = estimar_demanda(_periodos("P002", [50, 80]), ventana=6)

    assert resultado["producto_id"].tolist() == ["P002"]
    assert _demanda(resultado, "P002") == pytest.approx(65.0)


def test_producto_con_exactamente_la_ventana_usa_todos_los_periodos():
    resultado = estimar_demanda(
        _periodos("P001", [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]), ventana=6
    )

    assert _demanda(resultado, "P001") == pytest.approx(35.0)


def test_ventana_por_defecto_es_6_y_no_falla_la_validacion_de_ventana():
    """Sin el argumento se usa el default de config: int(6.0) == 6.

    El test se apoya en el default que expone la firma (no en una constante del
    módulo: ``VENTANA_DEFAULT`` se eliminó al parametrizar el módulo).
    """
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])

    por_defecto = estimar_demanda(historial)
    explicito = estimar_demanda(historial, ventana=6)

    pd.testing.assert_frame_equal(por_defecto, explicito)
    assert _demanda(por_defecto, "P001") == pytest.approx(613 / 6)


def test_ventana_1_devuelve_el_ultimo_periodo_por_fecha():
    """Con ventana=1 se toma el periodo más reciente, no la primera fila."""
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 111])
    desordenado = historial.iloc[[3, 0, 7, 5, 1, 6, 2, 4]]

    resultado = estimar_demanda(desordenado, ventana=1)

    assert _demanda(resultado, "P001") == pytest.approx(111.0)
    assert _demanda(resultado, "P001") != pytest.approx(100.0)


# ------------------------------------------------------ validación de entrada


@pytest.mark.parametrize("ventana", [0, -1])
def test_ventana_no_positiva_lanza_value_error(ventana):
    with pytest.raises(ValueError, match="ventana"):
        estimar_demanda(_periodos("P001", [10.0, 20.0]), ventana=ventana)


@pytest.mark.parametrize("ventana", ["6", 6.5])
def test_ventana_no_entera_lanza_value_error(ventana):
    with pytest.raises(ValueError, match="ventana"):
        estimar_demanda(_periodos("P001", [10.0, 20.0]), ventana=ventana)


def test_ventana_booleana_lanza_value_error():
    """True pasa isinstance(True, int) pero no es una ventana válida."""
    with pytest.raises(ValueError, match="ventana"):
        estimar_demanda(_periodos("P001", [10.0, 20.0]), ventana=True)


def test_dataframe_vacio_con_columnas_correctas_devuelve_vacio():
    vacio = pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "periodo": pd.Series(dtype=object),
            "cantidad_demandada": pd.Series(dtype="float64"),
        }
    )

    resultado = estimar_demanda(vacio)

    assert resultado.empty
    assert list(resultado.columns) == ["producto_id", "demanda_estimada"]
    assert resultado["producto_id"].dtype == object
    assert resultado["demanda_estimada"].dtype == "float64"
    assert resultado.index.tolist() == []


def test_dataframe_vacio_sin_columnas_lanza_value_error():
    with pytest.raises(ValueError, match="producto_id"):
        estimar_demanda(pd.DataFrame())


def test_dataframe_con_filas_sin_columnas_lanza_value_error():
    historial = pd.DataFrame({"producto_id": ["P001"], "periodo": ["2025-01-01"]})

    with pytest.raises(ValueError, match="cantidad_demandada"):
        estimar_demanda(historial)


def test_producto_sin_historial_no_aparece_en_la_salida():
    """La salida solo contiene los productos con filas en el historial."""
    resultado = estimar_demanda(_periodos("P001", [10.0, 20.0]), ventana=6)

    assert resultado["producto_id"].tolist() == ["P001"]
    assert "P002" not in set(resultado["producto_id"])


def test_producto_con_todos_los_periodos_en_cero():
    """Una demanda estimada de 0 es información válida, no un error."""
    resultado = estimar_demanda(_periodos("P001", [0.0, 0.0, 0.0]), ventana=6)

    assert resultado["producto_id"].tolist() == ["P001"]
    assert _demanda(resultado, "P001") == 0.0


def test_periodo_no_parseable_lanza_value_error_y_no_parser_error():
    historial = _historial(
        ["P001", "P001"], ["2025-01-01", "no-es-fecha"], [100.0, 105.0]
    )

    with pytest.raises(ValueError, match="fecha") as excepcion:
        estimar_demanda(historial)

    # El error nativo de pandas (DateParseError) ya es un ValueError: se
    # comprueba que el módulo relanza un ValueError propio en lugar de dejar
    # pasar el tipo nativo.
    assert type(excepcion.value) is ValueError
    assert not isinstance(excepcion.value, pd.errors.ParserError)


# ------------------------------------------- orden, pureza y tipo de periodo


def test_el_orden_de_las_filas_de_entrada_no_altera_el_resultado():
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])
    desordenado = historial.iloc[[5, 0, 3, 7, 1, 6, 2, 4]]

    pd.testing.assert_frame_equal(
        estimar_demanda(historial, ventana=3),
        estimar_demanda(desordenado, ventana=3),
    )


def test_los_periodos_se_ordenan_cronologicamente_no_por_aparicion():
    """Con filas desordenadas, la ventana toma los periodos más recientes.

    Las tres primeras filas de la entrada son agosto, enero y julio; si la
    ventana se tomara por orden de aparición el promedio daría 102.67.
    """
    desordenado = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100]).iloc[
        [7, 0, 6, 1, 5, 2, 4, 3]
    ]

    resultado = estimar_demanda(desordenado, ventana=3)

    assert _demanda(resultado, "P001") == pytest.approx(101.0)


def test_la_salida_esta_ordenada_por_producto_id():
    historial = _apilados(
        {
            "P003": [30.0, 30.0],
            "P001": [10.0, 10.0],
            "P002": [20.0, 20.0],
        }
    )

    resultado = estimar_demanda(historial, ventana=6)

    assert resultado["producto_id"].tolist() == ["P001", "P002", "P003"]
    assert resultado.index.tolist() == [0, 1, 2]


def test_no_modifica_el_dataframe_de_entrada():
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])
    copia = historial.copy(deep=True)

    estimar_demanda(historial, ventana=3)

    pd.testing.assert_frame_equal(historial, copia)
    assert historial["periodo"].dtype == copia["periodo"].dtype
    assert "demanda_estimada" not in historial.columns


def test_periodo_con_formato_string_se_parsea():
    como_texto = _historial(
        ["P001"] * 4,
        ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"],
        [100, 105, 98, 102],
    )

    resultado = estimar_demanda(como_texto, ventana=2)

    assert _demanda(resultado, "P001") == pytest.approx(100.0)
    pd.testing.assert_frame_equal(
        resultado, estimar_demanda(_periodos("P001", [100, 105, 98, 102]), ventana=2)
    )


def test_multiples_productos_se_calculan_por_separado():
    historial = _apilados(
        {
            "P001": [100, 105, 98, 102, 110, 95, 108, 100],
            "P002": [50, 80],
            "P003": [7.0],
        }
    )

    resultado = estimar_demanda(historial, ventana=6)

    assert resultado["producto_id"].tolist() == ["P001", "P002", "P003"]
    assert _demanda(resultado, "P001") == pytest.approx(613 / 6)
    assert _demanda(resultado, "P002") == pytest.approx(65.0)
    assert _demanda(resultado, "P003") == pytest.approx(7.0)


# ------------------------------------------------------------------- escala


def test_valores_muy_grandes_no_rompen_el_calculo():
    resultado = estimar_demanda(
        _periodos("P001", [1e12, 1.1e12, 0.9e12, 1.05e12]), ventana=3
    )

    assert _demanda(resultado, "P001") == pytest.approx(
        (1.1e12 + 0.9e12 + 1.05e12) / 3, rel=1e-9
    )


def test_valores_muy_pequenos_no_rompen_el_calculo():
    resultado = estimar_demanda(_periodos("P001", [1e-9, 1.2e-9, 0.8e-9]), ventana=3)

    assert _demanda(resultado, "P001") == pytest.approx(
        (1e-9 + 1.2e-9 + 0.8e-9) / 3, rel=1e-9
    )


# --------------------------------------------- ventana configurable (fase 4)


def test_ventana_3_promedia_solo_los_ultimos_3_periodos():
    """P001 con 8 periodos y ventana=3: media de [95, 108, 100] = 101.0.

    Quedan fuera los 5 periodos más antiguos. Con ventana 6 el promedio sería
    102.1667, así que el 101.0 demuestra que la ventana recorta de verdad.
    """
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])

    resultado = estimar_demanda(historial, ventana=3)

    assert _demanda(resultado, "P001") == pytest.approx((95 + 108 + 100) / 3)
    assert _demanda(resultado, "P001") == pytest.approx(101.0)
    assert _demanda(resultado, "P001") != pytest.approx(613 / 6)


def test_ventana_3_recorta_por_producto():
    """Con ventana=3 cada producto usa sus 3 periodos más recientes."""
    historial = _apilados(
        {
            "P001": [100, 105, 98, 102, 110, 95, 108, 100],
            "P002": [10.0, 20.0, 30.0, 40.0, 50.0],
            "P003": [1.0, 2.0],
        }
    )

    resultado = estimar_demanda(historial, ventana=3)

    assert _demanda(resultado, "P001") == pytest.approx(101.0)
    assert _demanda(resultado, "P002") == pytest.approx((30.0 + 40.0 + 50.0) / 3)
    # P003 tiene menos periodos que la ventana: se promedian los 2 disponibles.
    assert _demanda(resultado, "P003") == pytest.approx(1.5)


def test_ventana_12_usa_todos_los_periodos_disponibles():
    """Con 8 periodos y ventana=12 no se descarta nada: los 8 dan 102.25.

    Es distinto del 102.1667 de la ventana 6, así que el test fallaría si el
    argumento `ventana` se ignorara.
    """
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])

    resultado = estimar_demanda(historial, ventana=12)

    assert _demanda(resultado, "P001") == pytest.approx(818 / 8)
    assert _demanda(resultado, "P001") == pytest.approx(102.25)
    # Con todos los periodos dentro de la ventana, 12 y 8 dan lo mismo.
    assert _demanda(resultado, "P001") == pytest.approx(
        _demanda(estimar_demanda(historial, ventana=8), "P001")
    )


def test_ventana_1_usa_solo_el_ultimo_periodo_de_cada_producto():
    """Con ventana=1 la estimación es la demanda del periodo más reciente."""
    historial = _apilados(
        {
            "P001": [100, 105, 98, 102, 110, 95, 108, 120],
            "P002": [50, 80],
            "P003": [7.0],
        }
    )

    resultado = estimar_demanda(historial, ventana=1)

    assert resultado["producto_id"].tolist() == ["P001", "P002", "P003"]
    assert _demanda(resultado, "P001") == pytest.approx(120.0)
    assert _demanda(resultado, "P002") == pytest.approx(80.0)
    assert _demanda(resultado, "P003") == pytest.approx(7.0)


@pytest.mark.parametrize(
    ("ventana", "esperado"),
    [
        (1, 100.0),
        (3, 101.0),
        (6, 613 / 6),
        (8, 102.25),
        (12, 102.25),
    ],
)
def test_promedio_esperado_segun_la_ventana(ventana, esperado):
    """Mismo historial y distinta ventana: cambia el promedio esperado."""
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])

    resultado = estimar_demanda(historial, ventana=ventana)

    assert _demanda(resultado, "P001") == pytest.approx(esperado)


def test_el_default_de_ventana_viene_de_config_y_es_int():
    """El default de la firma es int(...) de PARAMETROS_DEFAULT, no un float.

    ``int(PARAMETROS_DEFAULT['demanda_ventana_default'])`` se evalúa al importar
    el módulo, así que con el valor de config (6.0) el default es el int 6 y la
    validación interna de `ventana` (``isinstance(ventana, int)``) no falla.
    """
    parametro = inspect.signature(estimar_demanda).parameters["ventana"]

    assert PARAMETROS_DEFAULT["demanda_ventana_default"] == 6.0
    assert parametro.default == PARAMETROS_DEFAULT["demanda_ventana_default"]
    assert isinstance(parametro.default, int)
    assert not isinstance(parametro.default, bool)
    assert parametro.default == 6
    assert parametro.annotation is int


def test_sin_ventana_equivale_a_pasar_el_default_de_config():
    """Llamar sin `ventana` y pasar el default de config dan lo mismo."""
    historial = _periodos("P001", [100, 105, 98, 102, 110, 95, 108, 100])

    pd.testing.assert_frame_equal(
        estimar_demanda(historial),
        estimar_demanda(
            historial, ventana=int(PARAMETROS_DEFAULT["demanda_ventana_default"])
        ),
    )
