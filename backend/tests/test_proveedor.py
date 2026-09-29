"""Tests unitarios del score de confiabilidad de proveedores (motor OR).

Solo pruebas de la función pura
``src.motor.proveedor.calcular_score_proveedor``: no se toca red, base de datos
ni archivos.

La última sección cubre los umbrales configurables (fase 4): los estados se
calculan con los cortes que recibe la función y sus valores por defecto se
leen de :data:`src.config.PARAMETROS_DEFAULT`.
"""

import inspect

import numpy as np
import pandas as pd
import pytest

from src.config import PARAMETROS_DEFAULT
from src.motor.proveedor import (
    COLUMNAS_REQUERIDAS,
    ESTADO_ACEPTABLE,
    ESTADO_CONFIABLE,
    ESTADO_RIESGOSO,
    PESO_CALIDAD,
    PESO_CUMPLIMIENTO,
    TOLERANCIA_SCORE,
    calcular_score_proveedor,
)


# ---------------------------------------------------------------- utilidades


def _proveedores(
    proveedor_id: list,
    cumplimiento_entrega_pct: list,
    tasa_defectos_pct: list,
    index: list | None = None,
) -> pd.DataFrame:
    """Construye el DataFrame de entrada mínimo que espera el motor."""
    return pd.DataFrame(
        {
            "proveedor_id": proveedor_id,
            "cumplimiento_entrega_pct": cumplimiento_entrega_pct,
            "tasa_defectos_pct": tasa_defectos_pct,
        },
        index=index,
    )


def _uno(cumplimiento: float, defectos: float) -> pd.DataFrame:
    """DataFrame de una sola fila, para los casos de frontera."""
    return _proveedores(["P001"], [cumplimiento], [defectos])


def _score_esperado(cumplimiento: float, defectos: float) -> float:
    """Score de referencia, calculado con la fórmula del enunciado."""
    return (
        cumplimiento * PESO_CUMPLIMIENTO + (100.0 - defectos) * PESO_CALIDAD
    )


def _por_proveedor(resultado: pd.DataFrame) -> pd.DataFrame:
    """Vista indexada por proveedor_id, para consultar sin depender del orden."""
    return resultado.set_index("proveedor_id")


def _score(resultado: pd.DataFrame, proveedor_id: str) -> float:
    """score del proveedor indicado."""
    return float(_por_proveedor(resultado).loc[proveedor_id, "score"])


def _estado(resultado: pd.DataFrame, proveedor_id: str) -> str:
    """estado del proveedor indicado."""
    return _por_proveedor(resultado).loc[proveedor_id, "estado"]


def _mapa_estados(resultado: pd.DataFrame) -> dict:
    """Devuelve {proveedor_id: estado}, sin depender del orden de las filas."""
    return dict(zip(resultado["proveedor_id"], resultado["estado"]))


# -------------------------------------------------------- constantes del módulo


def test_las_constantes_del_modulo_son_las_esperadas():
    """Pesos, tolerancia, columnas y etiquetas quedan fijados en el módulo.

    Los umbrales ya no son constantes de módulo: son parámetros de
    `calcular_score_proveedor` y se verifican en la sección de umbrales
    configurables (fase 4).
    """
    assert TOLERANCIA_SCORE == 1e-9
    assert PESO_CUMPLIMIENTO == 0.6
    assert PESO_CALIDAD == 0.4
    assert COLUMNAS_REQUERIDAS == (
        "proveedor_id",
        "cumplimiento_entrega_pct",
        "tasa_defectos_pct",
    )
    assert (ESTADO_CONFIABLE, ESTADO_ACEPTABLE, ESTADO_RIESGOSO) == (
        "Confiable",
        "Aceptable con reservas",
        "Riesgoso",
    )


# ------------------------------------------------------------ caso principal


def test_caso_normal_del_ejemplo_con_los_cuatro_proveedores():
    """A=96.2, B=86.0, C=76.0 y D=60.0, tal como en el enunciado."""
    resultado = calcular_score_proveedor(
        _proveedores(["A", "B", "C", "D"], [95, 82, 70, 50], [2, 8, 15, 25])
    )

    assert list(resultado.columns) == ["proveedor_id", "score", "estado"]
    assert resultado["proveedor_id"].tolist() == ["A", "B", "C", "D"]

    assert _score(resultado, "A") == pytest.approx(96.2)
    assert _score(resultado, "B") == pytest.approx(86.0)
    assert _score(resultado, "C") == pytest.approx(76.0)
    assert _score(resultado, "D") == pytest.approx(60.0)

    assert _mapa_estados(resultado) == {
        "A": ESTADO_CONFIABLE,
        "B": ESTADO_CONFIABLE,
        "C": ESTADO_ACEPTABLE,
        "D": ESTADO_ACEPTABLE,
    }


def test_el_calculo_vectorizado_coincide_con_la_formula_escalar():
    """Varias filas a la vez: cada score iguala el cálculo hecho a mano."""
    cumplimientos = [100.0, 95.0, 82.0, 70.0, 50.0, 0.0]
    defectos = [0.0, 2.0, 8.0, 15.0, 25.0, 100.0]
    ids = [f"P{i + 1:03d}" for i in range(len(cumplimientos))]
    resultado = calcular_score_proveedor(_proveedores(ids, cumplimientos, defectos))

    for proveedor_id, cumplimiento, defecto in zip(ids, cumplimientos, defectos):
        assert _score(resultado, proveedor_id) == pytest.approx(
            _score_esperado(cumplimiento, defecto)
        )


def test_cada_proveedor_recibe_su_propio_estado():
    """Un lote con los tres estados posibles: cada fila se clasifica sola."""
    resultado = calcular_score_proveedor(
        _proveedores(
            ["P001", "P002", "P003", "P004", "P005"],
            [100, 90, 75, 61, 10],
            [0, 10, 20, 41, 90],
        )
    )

    assert _mapa_estados(resultado) == {
        "P001": ESTADO_CONFIABLE,  # 100.0
        "P002": ESTADO_CONFIABLE,  # 90.0
        "P003": ESTADO_ACEPTABLE,  # 77.0
        "P004": ESTADO_ACEPTABLE,  # 60.2
        "P005": ESTADO_RIESGOSO,  # 10.0
    }
    assert set(resultado["estado"]) <= {
        ESTADO_CONFIABLE,
        ESTADO_ACEPTABLE,
        ESTADO_RIESGOSO,
    }


def test_acepta_columnas_de_tipo_entero():
    """Con insumos int64 el resultado es el mismo y el score sale float64."""
    entrada = _proveedores(["P001", "P002"], [95, 50], [2, 25])

    assert str(entrada["cumplimiento_entrega_pct"].dtype).startswith("int")

    resultado = calcular_score_proveedor(entrada)

    assert str(resultado["score"].dtype) == "float64"
    assert _score(resultado, "P001") == pytest.approx(96.2)
    assert _score(resultado, "P002") == pytest.approx(60.0)


# ------------------------------------------------------------------ fronteras


@pytest.mark.parametrize(
    ("cumplimiento", "defectos"),
    [(80.0, 20.0), (90.0, 35.0), (100.0, 50.0)],
)
def test_frontera_score_exactamente_80_es_confiable(
    cumplimiento: float, defectos: float
) -> None:
    """El corte de 80 es inclusivo: score == 80.0 es "Confiable"."""
    resultado = calcular_score_proveedor(_uno(cumplimiento, defectos))

    assert _score(resultado, "P001") == 80.0
    assert _estado(resultado, "P001") == ESTADO_CONFIABLE


@pytest.mark.parametrize(
    ("cumplimiento", "defectos"),
    [(50.0, 25.0), (60.0, 40.0), (100.0, 100.0)],
)
def test_frontera_score_exactamente_60_es_aceptable_con_reservas(
    cumplimiento: float, defectos: float
) -> None:
    """El corte de 60 pertenece al tramo aceptable: 60.0 no es riesgoso."""
    resultado = calcular_score_proveedor(_uno(cumplimiento, defectos))

    assert _score(resultado, "P001") == 60.0
    assert _estado(resultado, "P001") == ESTADO_ACEPTABLE


@pytest.mark.parametrize(
    ("cumplimiento", "defectos", "umbral", "estado"),
    [
        # Score matemático 60, representado como 59.99999999999999 (< 60): sin
        # la tolerancia caería en "Riesgoso" en lugar de "Aceptable".
        # El umbral se toma del default de config, que es el que usa la
        # función cuando no se le pasan umbrales.
        (
            96.0,
            94.0,
            PARAMETROS_DEFAULT["score_proveedor_riesgoso"],
            ESTADO_ACEPTABLE,
        ),
        # Score matemático 80, representado como 79.99999999939999 (< 80): sin
        # la tolerancia caería en "Aceptable con reservas".
        (
            79.999999999,
            20.0,
            PARAMETROS_DEFAULT["score_proveedor_confiable"],
            ESTADO_CONFIABLE,
        ),
    ],
)
def test_el_ruido_de_punto_flotante_en_los_cortes_no_cambia_el_estado(
    cumplimiento: float, defectos: float, umbral: float, estado: str
) -> None:
    """Cumplimiento 96 con defectos 94 (score matemático 60) es "Aceptable".

    Esa combinación da 59.99999999999999 en float64, es decir cae por debajo del
    corte de 60; gracias a TOLERANCIA_SCORE el estado es "Aceptable con
    reservas" y no "Riesgoso". El segundo caso comprueba lo mismo en el corte
    de 80.
    """
    resultado = calcular_score_proveedor(_uno(cumplimiento, defectos))

    score = _score(resultado, "P001")
    assert score == pytest.approx(umbral)  # el valor matemático está en el corte
    assert score < umbral  # pero float64 lo representa por debajo
    assert umbral - score <= TOLERANCIA_SCORE  # dentro de la banda tolerada
    assert _estado(resultado, "P001") == estado


@pytest.mark.parametrize(
    ("cumplimiento", "defectos", "score", "estado"),
    [
        (81.0, 21.0, 80.2, ESTADO_CONFIABLE),  # apenas por encima de 80
        (79.0, 19.0, 79.8, ESTADO_ACEPTABLE),  # apenas por debajo de 80
        (61.0, 41.0, 60.2, ESTADO_ACEPTABLE),  # apenas por encima de 60
        (59.0, 40.0, 59.4, ESTADO_RIESGOSO),  # apenas por debajo de 60
    ],
)
def test_fronteras_alrededor_de_los_umbrales(
    cumplimiento: float, defectos: float, score: float, estado: str
) -> None:
    """A un décimo de los umbrales el estado es el esperado en cada lado."""
    resultado = calcular_score_proveedor(_uno(cumplimiento, defectos))

    assert _score(resultado, "P001") == pytest.approx(score, abs=1e-9)
    assert _estado(resultado, "P001") == estado


def test_score_maximo_posible():
    """Cumplimiento 100 y defectos 0: score 100.0 y "Confiable"."""
    resultado = calcular_score_proveedor(_uno(100.0, 0.0))

    assert _score(resultado, "P001") == 100.0
    assert _estado(resultado, "P001") == ESTADO_CONFIABLE


def test_score_minimo_posible():
    """Cumplimiento 0 y defectos 100: score 0.0 y "Riesgoso"."""
    resultado = calcular_score_proveedor(_uno(0.0, 100.0))

    assert _score(resultado, "P001") == 0.0
    assert _estado(resultado, "P001") == ESTADO_RIESGOSO


# ---------------------------------------------------------------- vacío


def test_dataframe_vacio_con_columnas_devuelve_vacio_sin_error():
    """Sin filas pero con las columnas correctas: salida vacía y tipada."""
    vacio = pd.DataFrame(
        {
            "proveedor_id": pd.Series(dtype=object),
            "cumplimiento_entrega_pct": pd.Series(dtype="float64"),
            "tasa_defectos_pct": pd.Series(dtype="float64"),
        }
    )

    resultado = calcular_score_proveedor(vacio)

    assert resultado.empty
    assert list(resultado.columns) == ["proveedor_id", "score", "estado"]
    assert str(resultado["proveedor_id"].dtype) == "object"
    assert str(resultado["score"].dtype) == "float64"
    assert str(resultado["estado"].dtype) == "object"
    assert isinstance(resultado.index, pd.RangeIndex)
    assert list(resultado.index) == []


def test_dataframe_vacio_no_se_modifica_a_si_mismo():
    vacio = pd.DataFrame(
        {
            "proveedor_id": pd.Series(dtype=object),
            "cumplimiento_entrega_pct": pd.Series(dtype="float64"),
            "tasa_defectos_pct": pd.Series(dtype="float64"),
        }
    )
    copia = vacio.copy(deep=True)

    calcular_score_proveedor(vacio)

    pd.testing.assert_frame_equal(vacio, copia)


# --------------------------------------------------------- columnas faltantes


def test_dataframe_vacio_sin_columnas_lanza_valueerror():
    """Sin filas pero sin columnas también falla: la validación es estricta."""
    with pytest.raises(ValueError, match="faltan"):
        calcular_score_proveedor(pd.DataFrame())


def test_dataframe_con_filas_y_sin_columnas_lanza_valueerror():
    con_filas = pd.DataFrame({"otra_columna": ["P001", "P002"]})

    with pytest.raises(ValueError, match="proveedor_id"):
        calcular_score_proveedor(con_filas)


def test_el_mensaje_de_error_lista_las_tres_columnas_requeridas():
    with pytest.raises(ValueError) as error:
        calcular_score_proveedor(pd.DataFrame({"proveedor_id": ["P001"]}))

    mensaje = str(error.value)
    for columna in COLUMNAS_REQUERIDAS:
        assert columna in mensaje


@pytest.mark.parametrize("columna", COLUMNAS_REQUERIDAS)
def test_falta_una_columna_requerida_y_el_mensaje_la_nombra(columna: str):
    """Falta una sola columna: se falla igual con filas y sin filas."""
    completa = _proveedores(["P001"], [95.0], [2.0])
    sin_columna = completa.drop(columns=[columna])

    with pytest.raises(ValueError) as error:
        calcular_score_proveedor(sin_columna)
    assert columna in str(error.value)

    with pytest.raises(ValueError) as error_sin_filas:
        calcular_score_proveedor(sin_columna.head(0))
    assert columna in str(error_sin_filas.value)


# ------------------------------------------------------- orden y dtypes


def test_la_salida_esta_ordenada_por_proveedor_id_ascendente():
    resultado = calcular_score_proveedor(
        _proveedores(
            ["P003", "P001", "P004", "P002"], [70, 95, 50, 82], [15, 2, 25, 8]
        )
    )

    assert resultado["proveedor_id"].tolist() == ["P001", "P002", "P003", "P004"]


def test_el_orden_de_las_filas_de_entrada_no_altera_el_resultado():
    desordenado = _proveedores(["P003", "P001", "P002"], [70, 95, 82], [15, 2, 8])
    ordenado = _proveedores(["P001", "P002", "P003"], [95, 82, 70], [2, 8, 15])

    pd.testing.assert_frame_equal(
        calcular_score_proveedor(desordenado),
        calcular_score_proveedor(ordenado),
    )


def test_la_salida_tiene_rangeindex_desde_cero():
    """Un índice de entrada desordenado no se arrastra a la salida."""
    resultado = calcular_score_proveedor(
        _proveedores(["P002", "P001"], [82, 95], [8, 2], index=[5, 2])
    )

    assert list(resultado.index) == [0, 1]
    assert resultado["proveedor_id"].tolist() == ["P001", "P002"]


def test_dtypes_de_la_salida():
    """proveedor_id object, score float64 y estado object."""
    resultado = calcular_score_proveedor(
        _proveedores(["P001", "P002"], [95, 82], [2, 8])
    )

    assert str(resultado["proveedor_id"].dtype) == "object"
    assert str(resultado["score"].dtype) == "float64"
    assert str(resultado["estado"].dtype) == "object"
    assert all(isinstance(valor, str) for valor in resultado["estado"])


# ------------------------------------------------------------------- pureza


def test_no_modifica_el_dataframe_de_entrada():
    entrada = _proveedores(["P002", "P001"], [82.0, 95.0], [8.0, 2.0])
    copia = entrada.copy(deep=True)

    calcular_score_proveedor(entrada)

    pd.testing.assert_frame_equal(entrada, copia)
    assert list(entrada.columns) == list(COLUMNAS_REQUERIDAS)


def test_devuelve_un_dataframe_nuevo_e_independiente():
    """Modificar la salida no afecta a la entrada y viceversa."""
    entrada = _proveedores(["P001"], [95.0], [2.0])

    resultado = calcular_score_proveedor(entrada)
    resultado.loc[0, "score"] = 0.0

    assert float(entrada.iloc[0]["cumplimiento_entrega_pct"]) == 95.0
    assert _score(calcular_score_proveedor(entrada), "P001") == pytest.approx(96.2)


# ------------------------------------------------------- valores extremos


def test_valores_muy_grandes_no_rompen_el_calculo():
    """Magnitud fuera del rango del schema: la aritmética sigue siendo finita.

    El schema garantiza [0, 100] y este módulo no valida el rango por diseño.
    La prueba solo verifica que no hay excepción, NaN ni infinito, y que el
    score respeta la fórmula; con insumos fuera de rango el score no tiene por
    qué quedar dentro de [0, 100].
    """
    grande = 1.0e12
    resultado = calcular_score_proveedor(_uno(grande, 0.0))

    score = _score(resultado, "P001")
    assert np.isfinite(score)
    assert score == pytest.approx(
        grande * PESO_CUMPLIMIENTO + 100.0 * PESO_CALIDAD
    )
    assert _estado(resultado, "P001") == ESTADO_CONFIABLE


def test_valores_muy_pequenos_no_rompen_el_calculo():
    """Valor positivo diminuto: score finito (sin underflow a 0 indebido)."""
    diminuto = 1.0e-9
    resultado = calcular_score_proveedor(_uno(diminuto, 100.0))

    score = _score(resultado, "P001")
    assert np.isfinite(score)
    assert score == pytest.approx(diminuto * PESO_CUMPLIMIENTO)
    assert _estado(resultado, "P001") == ESTADO_RIESGOSO


# ------------------------------------------- umbrales configurables (fase 4)


def test_los_defaults_de_los_umbrales_vienen_de_config():
    """Sin argumentos se usan los umbrales de PARAMETROS_DEFAULT (80 y 60)."""
    parametros = inspect.signature(calcular_score_proveedor).parameters

    assert parametros["umbral_confiable"].default == (
        PARAMETROS_DEFAULT["score_proveedor_confiable"]
    )
    assert parametros["umbral_riesgoso"].default == (
        PARAMETROS_DEFAULT["score_proveedor_riesgoso"]
    )
    # Y los valores de config siguen siendo los históricos del módulo.
    assert PARAMETROS_DEFAULT["score_proveedor_confiable"] == 80.0
    assert PARAMETROS_DEFAULT["score_proveedor_riesgoso"] == 60.0


def test_el_default_de_umbral_confiable_es_80():
    """El default de `umbral_confiable` es 80.0, leído de la firma."""
    parametro = inspect.signature(calcular_score_proveedor).parameters[
        "umbral_confiable"
    ]

    assert parametro.default == 80.0
    assert parametro.default == PARAMETROS_DEFAULT["score_proveedor_confiable"]
    assert isinstance(parametro.default, float)
    assert not isinstance(parametro.default, bool)
    assert parametro.annotation is float


def test_el_default_de_umbral_riesgoso_es_60():
    """El default de `umbral_riesgoso` es 60.0, leído de la firma."""
    parametro = inspect.signature(calcular_score_proveedor).parameters[
        "umbral_riesgoso"
    ]

    assert parametro.default == 60.0
    assert parametro.default == PARAMETROS_DEFAULT["score_proveedor_riesgoso"]
    assert isinstance(parametro.default, float)
    assert not isinstance(parametro.default, bool)
    assert parametro.annotation is float


def test_sin_umbrales_equivale_a_pasar_los_defaults_de_config():
    """Llamar sin umbrales y pasar 80.0 / 60.0 dan exactamente lo mismo."""
    proveedores = _proveedores(
        ["P001", "P002", "P003"], [95, 70, 50], [2, 15, 25]
    )

    pd.testing.assert_frame_equal(
        calcular_score_proveedor(proveedores),
        calcular_score_proveedor(
            proveedores,
            umbral_confiable=PARAMETROS_DEFAULT["score_proveedor_confiable"],
            umbral_riesgoso=PARAMETROS_DEFAULT["score_proveedor_riesgoso"],
        ),
    )


def test_umbral_confiable_custom_90_reclasifica_el_proveedor_de_85():
    """Score 85: "Confiable" con el default (80) y "Aceptable" con 90."""
    proveedores = _uno(85.0, 15.0)

    por_defecto = calcular_score_proveedor(proveedores)
    custom = calcular_score_proveedor(proveedores, umbral_confiable=90.0)

    assert _score(por_defecto, "P001") == pytest.approx(85.0)
    assert _estado(por_defecto, "P001") == ESTADO_CONFIABLE
    assert _mapa_estados(custom) == {"P001": ESTADO_ACEPTABLE}
    # El umbral solo mueve la clasificación: el score es el mismo.
    pd.testing.assert_series_equal(custom["score"], por_defecto["score"])


def test_umbral_riesgoso_custom_70_reclasifica_el_proveedor_de_65():
    """Score 65: "Aceptable" con el default (60) y "Riesgoso" con 70."""
    proveedores = _uno(65.0, 35.0)

    por_defecto = calcular_score_proveedor(proveedores)
    custom = calcular_score_proveedor(proveedores, umbral_riesgoso=70.0)

    assert _score(por_defecto, "P001") == pytest.approx(65.0)
    assert _estado(por_defecto, "P001") == ESTADO_ACEPTABLE
    assert _mapa_estados(custom) == {"P001": ESTADO_RIESGOSO}
    pd.testing.assert_series_equal(custom["score"], por_defecto["score"])


def test_ambos_umbrales_custom_a_la_vez_clasifican_los_tres_tramos():
    """Con 90 y 70 los scores 100, 85 y 65 caen en los tres estados."""
    proveedores = _proveedores(
        ["P001", "P002", "P003"], [100, 85, 65], [0, 15, 35]
    )

    por_defecto = calcular_score_proveedor(proveedores)
    custom = calcular_score_proveedor(
        proveedores, umbral_confiable=90.0, umbral_riesgoso=70.0
    )

    assert _mapa_estados(por_defecto) == {
        "P001": ESTADO_CONFIABLE,  # 100.0
        "P002": ESTADO_CONFIABLE,  # 85.0
        "P003": ESTADO_ACEPTABLE,  # 65.0
    }
    assert _mapa_estados(custom) == {
        "P001": ESTADO_CONFIABLE,  # 100.0 >= 90
        "P002": ESTADO_ACEPTABLE,  # 70 <= 85.0 < 90
        "P003": ESTADO_RIESGOSO,  # 65.0 < 70
    }
    assert list(custom.columns) == ["proveedor_id", "score", "estado"]
    assert set(custom["estado"]) == {
        ESTADO_CONFIABLE,
        ESTADO_ACEPTABLE,
        ESTADO_RIESGOSO,
    }
    # Con umbrales custom los scores no cambian: solo los cortes.
    pd.testing.assert_series_equal(custom["score"], por_defecto["score"])


def test_umbrales_custom_respetan_las_fronteras_exactas():
    """Los cortes custom son inclusivos: 90 es "Confiable" y 70 "Aceptable"."""
    exacto_confiable = _uno(100.0, 25.0)  # score 90.0
    exacto_riesgoso = _uno(70.0, 30.0)  # score 70.0

    resultado_confiable = calcular_score_proveedor(
        exacto_confiable, umbral_confiable=90.0, umbral_riesgoso=70.0
    )
    resultado_riesgoso = calcular_score_proveedor(
        exacto_riesgoso, umbral_confiable=90.0, umbral_riesgoso=70.0
    )

    assert _score(resultado_confiable, "P001") == 90.0
    assert _estado(resultado_confiable, "P001") == ESTADO_CONFIABLE
    assert _score(resultado_riesgoso, "P001") == 70.0
    assert _estado(resultado_riesgoso, "P001") == ESTADO_ACEPTABLE


def test_umbrales_invertidos_dejan_vacia_la_banda_aceptable():
    """Documentado: con umbral_confiable <= umbral_riesgoso no hay banda media.

    Con esos cortes ningún proveedor queda en "Aceptable con reservas".
    """
    proveedores = _proveedores(["P001", "P002"], [95, 50], [2, 30])

    resultado = calcular_score_proveedor(
        proveedores, umbral_confiable=60.0, umbral_riesgoso=80.0
    )

    assert _mapa_estados(resultado) == {
        "P001": ESTADO_CONFIABLE,  # 96.2 >= 60
        "P002": ESTADO_RIESGOSO,  # 58.0 < 80
    }
    assert ESTADO_ACEPTABLE not in set(resultado["estado"])


def test_umbrales_extremos_no_dejan_tramos_inalcanzables():
    """Documentado: con umbral_confiable > 100 no hay "Confiable" y con
    umbral_riesgoso <= 0 no hay "Riesgoso" (scores dentro del rango 0-100).
    """
    proveedores = _proveedores(["P001", "P002"], [100, 0], [0, 100])

    sin_confiables = calcular_score_proveedor(
        proveedores, umbral_confiable=150.0
    )
    sin_riesgosos = calcular_score_proveedor(proveedores, umbral_riesgoso=0.0)

    assert _mapa_estados(sin_confiables) == {
        "P001": ESTADO_ACEPTABLE,  # 100.0 < 150
        "P002": ESTADO_RIESGOSO,  # 0.0 < 60
    }
    assert ESTADO_CONFIABLE not in set(sin_confiables["estado"])

    assert _mapa_estados(sin_riesgosos) == {
        "P001": ESTADO_CONFIABLE,  # 100.0 >= 80
        "P002": ESTADO_ACEPTABLE,  # 0.0 >= 0 - 1e-9
    }
    assert ESTADO_RIESGOSO not in set(sin_riesgosos["estado"])

