"""Tests unitarios de la clasificación XYZ del motor OR.

Solo pruebas de la función pura ``src.motor.xyz.clasificar_xyz``: no se toca
red, base de datos ni archivos.

Los umbrales de corte ya no son constantes del módulo (``UMBRAL_X`` y
``UMBRAL_Y`` se eliminaron al parametrizar el módulo en la fase 4): los tests
los leen de la firma de ``clasificar_xyz``, que a su vez los lee de
:data:`src.config.PARAMETROS_DEFAULT`.
"""

import inspect

import numpy as np
import pandas as pd
import pytest

from src.config import PARAMETROS_DEFAULT
from src.motor.xyz import (
    TOLERANCIA_CV,
    clasificar_xyz,
)

# Umbrales por defecto del motor, leídos de la propia firma: los tests de cortes
# se refieren así al default real que usa clasificar_xyz y no a una copia local
# del valor (mismo criterio que test_demanda.py y test_proveedor.py).
_FIRMA = inspect.signature(clasificar_xyz).parameters
UMBRAL_X: float = _FIRMA["umbral_x"].default
UMBRAL_Y: float = _FIRMA["umbral_y"].default


# ---------------------------------------------------------------- utilidades


def _historial(producto_id: list, cantidad_demandada: list) -> pd.DataFrame:
    """Construye el DataFrame de entrada mínimo que espera el motor."""
    return pd.DataFrame(
        {
            "producto_id": producto_id,
            "cantidad_demandada": cantidad_demandada,
        }
    )


def _periodos(producto_id: str, cantidades: list) -> pd.DataFrame:
    """Historial de un solo producto, con una fila por periodo."""
    return _historial([producto_id] * len(cantidades), list(cantidades))


def _apilados(por_producto: dict) -> pd.DataFrame:
    """Concatena varios productos {producto_id: [cantidades]}.

    Las filas de cada producto van en bloque, para que el orden de entrada sea
    distinto del orden de salida esperado (producto_id ascendente).
    """
    partes = [_periodos(pid, cantidades) for pid, cantidades in por_producto.items()]
    return pd.concat(partes, ignore_index=True)


def _por_producto(resultado: pd.DataFrame) -> pd.DataFrame:
    """Vista indexada por producto_id, para consultar sin depender del orden."""
    return resultado.set_index("producto_id")


def _clase(resultado: pd.DataFrame, producto_id: str):
    """clase_xyz del producto indicado."""
    return _por_producto(resultado).loc[producto_id, "clase_xyz"]


def _cv(resultado: pd.DataFrame, producto_id: str):
    """cv del producto indicado, tal cual (puede ser None)."""
    return _por_producto(resultado).loc[producto_id, "cv"]


def _dos_periodos_con_cv(
    cv_objetivo: float, producto_id: str = "P1", base: float = 100.0
) -> pd.DataFrame:
    """Historial de dos periodos cuya CV muestral es ``cv_objetivo``.

    Para dos valores 0 < a < b se cumple CV = (b - a) * sqrt(2) / (a + b);
    despejando b queda b = a * (sqrt(2) + cv) / (sqrt(2) - cv). Sirve para
    construir CV justo en los umbrales (0.5 y 1.0) con error de redondeo
    despreciable frente a la tolerancia.
    """
    raiz_de_dos = float(np.sqrt(2.0))
    demandas = [base, base * (raiz_de_dos + cv_objetivo) / (raiz_de_dos - cv_objetivo)]
    return _periodos(producto_id, demandas)


def _cv_manual(cantidades: list) -> float:
    """CV de referencia, calculado con pandas (std muestral, ddof=1)."""
    serie = pd.Series(cantidades, dtype="float64")
    return float(serie.std(ddof=1) / serie.mean())


# ------------------------------------------------------------ caso principal


def test_caso_normal_del_ejemplo():
    """P001 -> X, P002 -> Y, P003 -> Z (los tres perfiles del ejemplo)."""
    historial = _apilados(
        {
            "P001": [100.0, 105.0, 98.0, 102.0],
            "P002": [50.0, 300.0, 80.0, 450.0],
            "P003": [10.0, 200.0, 15.0, 180.0],
        }
    )

    resultado = clasificar_xyz(historial)

    assert list(resultado["producto_id"]) == ["P001", "P002", "P003"]
    assert list(resultado["clase_xyz"]) == ["X", "Y", "Z"]
    # CV muestrales: 2.9861/101.25, 189.5609/220 y 102.8247/101.25.
    assert _cv(resultado, "P001") == pytest.approx(0.0295, rel=1e-3)
    assert _cv(resultado, "P002") == pytest.approx(0.8616, rel=1e-3)
    assert _cv(resultado, "P003") == pytest.approx(1.0156, rel=1e-3)


def test_devuelve_solo_las_tres_columnas_de_la_salida():
    resultado = clasificar_xyz(_periodos("P001", [100.0, 102.0]))

    assert list(resultado.columns) == ["producto_id", "cv", "clase_xyz"]


def test_las_etiquetas_son_solo_x_y_o_z():
    resultado = clasificar_xyz(
        _apilados(
            {
                "P001": [100.0, 105.0, 98.0, 102.0],
                "P002": [50.0, 300.0, 80.0, 450.0],
                "P003": [10.0, 200.0, 15.0, 180.0],
            }
        )
    )

    assert set(resultado["clase_xyz"]) <= {"X", "Y", "Z"}


def test_acepta_columnas_de_tipo_entero():
    """Con enteros el CV debe ser el mismo que con floats."""
    resultado = clasificar_xyz(_periodos("P001", [100, 105, 98, 102]))

    assert _cv(resultado, "P001") == pytest.approx(0.0295, rel=1e-3)
    assert _clase(resultado, "P001") == "X"


def test_el_orden_de_las_filas_de_entrada_no_altera_el_resultado():
    """El cálculo agrupa por producto: el orden de entrada es irrelevante."""
    intercalado = _historial(
        ["P002", "P001", "P002", "P001"],
        [50.0, 100.0, 300.0, 105.0],
    )

    resultado = clasificar_xyz(intercalado)

    assert list(resultado["producto_id"]) == ["P001", "P002"]
    assert _cv(resultado, "P001") == pytest.approx(_cv_manual([100.0, 105.0]), rel=1e-9)
    assert _cv(resultado, "P002") == pytest.approx(_cv_manual([50.0, 300.0]), rel=1e-9)


# -------------------------------------------------- desviación estándar (ddof)


def test_usa_desviacion_estandar_muestral_y_no_poblacional():
    """Con 2 periodos y ddof=1 el CV es sqrt(2)/3, no 1/3."""
    resultado = clasificar_xyz(_periodos("P001", [2.0, 4.0]))

    muestral = pd.Series([2.0, 4.0])
    esperado_muestral = float(muestral.std(ddof=1) / muestral.mean())
    esperado_poblacional = float(muestral.std(ddof=0) / muestral.mean())

    assert esperado_muestral == pytest.approx(np.sqrt(2.0) / 3.0, rel=1e-12)
    assert _cv(resultado, "P001") == pytest.approx(esperado_muestral, rel=1e-9)
    assert _cv(resultado, "P001") != pytest.approx(esperado_poblacional, rel=1e-9)


# ------------------------------------------------------- cortes de clase X/Y/Z


def test_cv_bajo_el_umbral_es_clase_x():
    resultado = clasificar_xyz(_dos_periodos_con_cv(0.1))

    assert _cv(resultado, "P1") == pytest.approx(0.1, rel=1e-6)
    assert _clase(resultado, "P1") == "X"


def test_cv_exactamente_el_umbral_x_es_clase_x():
    """El corte de X es inclusivo: CV == 0.5 pertenece a X."""
    resultado = clasificar_xyz(_dos_periodos_con_cv(UMBRAL_X))

    assert _cv(resultado, "P1") == pytest.approx(UMBRAL_X, abs=1e-9)
    assert _clase(resultado, "P1") == "X"


def test_cv_apenas_sobre_el_umbral_x_dentro_de_la_tolerancia_es_clase_x():
    """El ruido de punto flotante en el corte no debe degradar a Y."""
    resultado = clasificar_xyz(_dos_periodos_con_cv(UMBRAL_X + TOLERANCIA_CV / 10.0))

    # El CV supera el umbral, pero por menos que la tolerancia permitida.
    assert _cv(resultado, "P1") > UMBRAL_X
    assert _cv(resultado, "P1") <= UMBRAL_X + TOLERANCIA_CV
    assert _clase(resultado, "P1") == "X"


def test_cv_sobre_el_umbral_x_es_clase_y():
    resultado = clasificar_xyz(_dos_periodos_con_cv(UMBRAL_X + 1e-3))

    assert _clase(resultado, "P1") == "Y"


def test_cv_exactamente_el_umbral_y_es_clase_y():
    """El corte de Y es inclusivo: CV == 1.0 pertenece a Y, no a Z."""
    resultado = clasificar_xyz(_dos_periodos_con_cv(UMBRAL_Y))

    assert _cv(resultado, "P1") == pytest.approx(UMBRAL_Y, abs=1e-9)
    assert _clase(resultado, "P1") == "Y"


def test_cv_sobre_el_umbral_y_es_clase_z():
    resultado = clasificar_xyz(_dos_periodos_con_cv(UMBRAL_Y + 1e-3))

    assert _clase(resultado, "P1") == "Z"


def test_los_tres_tramos_se_cubren_en_una_misma_llamada():
    historial = pd.concat(
        [
            _dos_periodos_con_cv(UMBRAL_X, producto_id="X1"),
            _dos_periodos_con_cv(0.75, producto_id="Y1"),
            _dos_periodos_con_cv(UMBRAL_Y + 1e-3, producto_id="Z1"),
        ],
        ignore_index=True,
    )

    resultado = clasificar_xyz(historial)

    assert list(resultado["clase_xyz"]) == ["X", "Y", "Z"]


# ------------------------------------------------- desviación cero y media cero


def test_desviacion_cero_con_media_positiva_es_clase_x():
    """Demanda constante: CV exactamente 0 y clase X."""
    resultado = clasificar_xyz(_periodos("P001", [7.0, 7.0, 7.0, 7.0]))

    assert _cv(resultado, "P001") == 0.0
    assert isinstance(_cv(resultado, "P001"), float)
    assert _clase(resultado, "P001") == "X"


def test_los_periodos_en_cero_cuentan_en_el_calculo():
    """Los ceros son periodos válidos: [0, 0, 0, 100] tiene CV 2.0 -> Z."""
    resultado = clasificar_xyz(_periodos("P001", [0.0, 0.0, 0.0, 100.0]))

    assert _cv(resultado, "P001") == pytest.approx(2.0, rel=1e-9)
    assert _clase(resultado, "P001") == "Z"


def test_media_cero_da_cv_y_clase_nulos_sin_excepcion():
    resultado = clasificar_xyz(_periodos("P001", [0.0, 0.0, 0.0, 0.0]))

    assert list(resultado["producto_id"]) == ["P001"]
    assert _cv(resultado, "P001") is None
    assert _clase(resultado, "P001") is None


def test_media_cero_convive_con_productos_clasificables():
    """Un producto sin CV no debe contaminar ni romper al resto."""
    historial = _apilados(
        {
            "P001": [0.0, 0.0],
            "P002": [100.0, 105.0, 98.0, 102.0],
        }
    )

    resultado = clasificar_xyz(historial)

    assert _cv(resultado, "P001") is None
    assert _clase(resultado, "P001") is None
    assert _cv(resultado, "P002") == pytest.approx(0.0295, rel=1e-3)
    assert _clase(resultado, "P002") == "X"


def test_dos_periodos_en_cero_tambien_dan_cv_nulo():
    """Con 2 periodos sí hay desviación muestral, pero la media es 0."""
    resultado = clasificar_xyz(_periodos("P001", [0.0, 0.0]))

    assert _cv(resultado, "P001") is None
    assert _clase(resultado, "P001") is None


# --------------------------------------------------------- exclusiones


def test_producto_con_un_solo_periodo_se_excluye():
    """Sin 2 observaciones no hay desviación muestral posible."""
    historial = _apilados(
        {
            "P001": [100.0],
            "P002": [100.0, 105.0, 98.0, 102.0],
        }
    )

    resultado = clasificar_xyz(historial)

    assert list(resultado["producto_id"]) == ["P002"]
    assert "P001" not in set(resultado["producto_id"])


def test_producto_sin_historial_no_aparece():
    """Un producto sin ninguna fila no puede aparecer en la salida."""
    historial = _apilados(
        {
            "P001": [100.0, 105.0],
            "P002": [50.0, 60.0],
        }
    )

    resultado = clasificar_xyz(historial)

    assert list(resultado["producto_id"]) == ["P001", "P002"]
    assert "P999" not in set(resultado["producto_id"])


def test_historial_de_una_sola_fila_devuelve_salida_vacia():
    resultado = clasificar_xyz(_periodos("P001", [100.0]))

    assert resultado.empty
    assert list(resultado.columns) == ["producto_id", "cv", "clase_xyz"]


def test_un_periodo_nulo_no_cuenta_como_historia_suficiente():
    """[10, None] es un solo periodo observado: el producto se excluye."""
    resultado = clasificar_xyz(_periodos("P001", [10.0, None]))

    assert resultado.empty


def test_los_periodos_nulos_no_cuentan_pero_no_rompen_el_calculo():
    """[10, None, 30] son 2 observaciones válidas: CV de [10, 30]."""
    resultado = clasificar_xyz(_periodos("P001", [10.0, None, 30.0]))

    assert list(resultado["producto_id"]) == ["P001"]
    assert _cv(resultado, "P001") == pytest.approx(_cv_manual([10.0, 30.0]), rel=1e-9)
    assert _clase(resultado, "P001") == "Y"


# ------------------------------------------------------------------ vacío


def test_dataframe_vacio_con_columnas_devuelve_vacio_sin_error():
    vacio = pd.DataFrame(
        {
            "producto_id": pd.Series(dtype=object),
            "cantidad_demandada": pd.Series(dtype="float64"),
        }
    )

    resultado = clasificar_xyz(vacio)

    assert resultado.empty
    assert list(resultado.columns) == ["producto_id", "cv", "clase_xyz"]
    assert resultado["producto_id"].dtype == object
    assert resultado["clase_xyz"].dtype == object
    assert pd.api.types.is_float_dtype(resultado["cv"])


def test_dataframe_vacio_sin_columnas_lanza_value_error():
    with pytest.raises(ValueError):
        clasificar_xyz(pd.DataFrame())


def test_dataframe_vacio_sin_columnas_reporta_las_que_faltan():
    with pytest.raises(ValueError, match="cantidad_demandada"):
        clasificar_xyz(pd.DataFrame())

    with pytest.raises(ValueError, match="producto_id"):
        clasificar_xyz(pd.DataFrame())


def test_dataframe_vacio_con_una_sola_columna_lanza_value_error():
    """La validación es estricta: tener una columna no basta, y no hay filas."""
    con_producto_id = pd.DataFrame({"producto_id": pd.Series(dtype=object)})
    con_cantidades = pd.DataFrame({"cantidad_demandada": pd.Series(dtype="float64")})

    with pytest.raises(ValueError, match="cantidad_demandada"):
        clasificar_xyz(con_producto_id)

    with pytest.raises(ValueError, match="producto_id"):
        clasificar_xyz(con_cantidades)


def test_dataframe_con_filas_y_sin_columnas_lanza_value_error():
    con_filas = pd.DataFrame({"otra": ["P001", "P002"], "demanda": [1.0, 2.0]})

    with pytest.raises(ValueError) as error:
        clasificar_xyz(con_filas)

    mensaje = str(error.value)
    assert "producto_id" in mensaje
    assert "cantidad_demandada" in mensaje


def test_dataframe_con_filas_y_sin_una_columna_lanza_value_error():
    sin_cantidades = pd.DataFrame({"producto_id": ["P001", "P002"]})

    with pytest.raises(ValueError, match="cantidad_demandada"):
        clasificar_xyz(sin_cantidades)


def test_el_mensaje_de_error_nombra_todas_las_columnas_requeridas():
    with pytest.raises(ValueError) as error:
        clasificar_xyz(pd.DataFrame({"otra": [1.0]}))

    mensaje = str(error.value)
    assert "clasificar_xyz" in mensaje
    assert "producto_id, cantidad_demandada" in mensaje


# -------------------------------------------------------- orden determinista


def test_la_salida_esta_ordenada_por_producto_id_ascendente():
    historial = _apilados(
        {
            "P003": [10.0, 200.0, 15.0, 180.0],
            "P001": [100.0, 105.0, 98.0, 102.0],
            "P002": [50.0, 300.0, 80.0, 450.0],
        }
    )

    resultado = clasificar_xyz(historial)

    assert list(resultado["producto_id"]) == ["P001", "P002", "P003"]
    assert list(resultado["clase_xyz"]) == ["X", "Y", "Z"]


def test_el_orden_de_salida_no_depende_del_orden_de_entrada():
    poblacion_1 = {
        "P010": [100.0, 105.0, 98.0, 102.0],
        "P002": [50.0, 300.0, 80.0, 450.0],
        "P100": [10.0, 200.0, 15.0, 180.0],
    }
    poblacion_2 = {
        "P100": [10.0, 200.0, 15.0, 180.0],
        "P010": [100.0, 105.0, 98.0, 102.0],
        "P002": [50.0, 300.0, 80.0, 450.0],
    }

    primera = clasificar_xyz(_apilados(poblacion_1))
    segunda = clasificar_xyz(_apilados(poblacion_2))

    pd.testing.assert_frame_equal(primera, segunda)
    assert list(primera["producto_id"]) == ["P002", "P010", "P100"]
    # El orden por producto_id es de texto: 'P100' va después de 'P010'.
    assert list(primera["clase_xyz"]) == ["Y", "X", "Z"]


def test_el_indice_de_salida_es_un_rango_nuevo():
    resultado = clasificar_xyz(_periodos("P001", [100.0, 105.0]))

    assert resultado.index.tolist() == [0]


def test_dtypes_de_la_salida_con_filas():
    resultado = clasificar_xyz(
        _apilados({"P001": [0.0, 0.0], "P002": [100.0, 105.0]})
    )

    assert resultado["producto_id"].dtype == object
    assert resultado["cv"].dtype == object
    assert resultado["clase_xyz"].dtype == object
    # Un CV calculable es un float de Python (no un numpy escalar ni NaN).
    assert isinstance(_cv(resultado, "P002"), float)
    assert _cv(resultado, "P001") is None
    assert isinstance(_clase(resultado, "P002"), str)


# ---------------------------------------------- pureza y validación de entrada


def test_no_modifica_el_dataframe_de_entrada():
    historial = _apilados(
        {"P002": [50.0, 300.0, 80.0, 450.0], "P001": [100.0, 105.0, 98.0, 102.0]}
    )
    copia = historial.copy(deep=True)

    clasificar_xyz(historial)

    pd.testing.assert_frame_equal(historial, copia)
    assert list(historial.columns) == ["producto_id", "cantidad_demandada"]
    assert "cv" not in historial.columns


def test_no_modifica_un_dataframe_de_entrada_ya_usado():
    """Llamar dos veces con la misma entrada da el mismo resultado."""
    historial = _apilados({"P001": [100.0, 105.0], "P002": [0.0, 0.0]})

    primera = clasificar_xyz(historial)
    segunda = clasificar_xyz(historial)

    pd.testing.assert_frame_equal(primera, segunda)


# ------------------------------------------------------------------- escala


def test_valores_muy_grandes_no_rompen_el_calculo():
    resultado = clasificar_xyz(_periodos("P001", [1e12, 1.05e12]))

    assert _cv(resultado, "P001") == pytest.approx(
        _cv_manual([1e12, 1.05e12]), rel=1e-9
    )
    assert _clase(resultado, "P001") == "X"


def test_valores_muy_pequenos_no_rompen_el_calculo():
    resultado = clasificar_xyz(_periodos("P001", [1e-9, 1.05e-9]))

    assert _cv(resultado, "P001") == pytest.approx(
        _cv_manual([1e-9, 1.05e-9]), rel=1e-9
    )
    assert _clase(resultado, "P001") == "X"


def test_el_cv_no_depende_de_la_escala_de_la_demanda():
    """Multiplicar toda la demanda por una constante deja el CV igual."""
    base = clasificar_xyz(_periodos("P001", [100.0, 105.0, 98.0, 102.0]))
    escalada = clasificar_xyz(_periodos("P001", [1e8, 1.05e8, 9.8e7, 1.02e8]))

    assert _cv(escalada, "P001") == pytest.approx(_cv(base, "P001"), rel=1e-9)
    assert _clase(escalada, "P001") == "X"


def test_escalas_distintas_entre_productos_dan_las_mismas_clases():
    historial = _apilados(
        {
            "P001": [100.0, 105.0, 98.0, 102.0],
            "P002": [1e-6, 2.1e-6, 1.6e-6, 9e-6],
        }
    )

    resultado = clasificar_xyz(historial)

    assert _cv(resultado, "P002") == pytest.approx(
        _cv_manual([1e-6, 2.1e-6, 1.6e-6, 9e-6]), rel=1e-9
    )
    assert _clase(resultado, "P001") == "X"
    assert _clase(resultado, "P002") == "Z"


def test_muchos_productos_coinciden_con_el_calculo_manual():
    """Comprobación de preservación de datos sobre un catálogo variado."""
    poblacion = {
        "P001": [100.0, 105.0, 98.0, 102.0],
        "P002": [50.0, 300.0, 80.0, 450.0],
        "P003": [10.0, 200.0, 15.0, 180.0],
        "P004": [7.0, 7.0, 7.0],
        "P005": [0.0, 0.0, 0.0],
        "P006": [0.0, 0.0, 0.0, 100.0],
    }

    resultado = clasificar_xyz(_apilados(poblacion))

    assert list(resultado["producto_id"]) == list(poblacion)
    for producto_id, cantidades in poblacion.items():
        if set(cantidades) == {0.0}:
            assert _cv(resultado, producto_id) is None
            assert _clase(resultado, producto_id) is None
        else:
            assert _cv(resultado, producto_id) == pytest.approx(
                _cv_manual(cantidades), rel=1e-3
            )


# ------------------------------------------- umbrales configurables (fase 4)


def test_los_defaults_de_los_umbrales_vienen_de_config():
    """Sin argumentos se usan los umbrales de PARAMETROS_DEFAULT (0.5 y 1.0)."""
    parametros = inspect.signature(clasificar_xyz).parameters

    assert parametros["umbral_x"].default == PARAMETROS_DEFAULT["cv_confianza_alta"]
    assert parametros["umbral_y"].default == PARAMETROS_DEFAULT["cv_confianza_media"]
    # Y los valores de config siguen siendo los históricos del módulo.
    assert PARAMETROS_DEFAULT["cv_confianza_alta"] == 0.5
    assert PARAMETROS_DEFAULT["cv_confianza_media"] == 1.0


def test_el_default_de_umbral_x_es_0_5_leido_de_la_firma():
    """El default de `umbral_x` es 0.5, leído de la firma."""
    parametro = inspect.signature(clasificar_xyz).parameters["umbral_x"]

    assert parametro.default == 0.5
    assert parametro.default == PARAMETROS_DEFAULT["cv_confianza_alta"]
    assert isinstance(parametro.default, float)
    assert not isinstance(parametro.default, bool)
    assert parametro.annotation is float


def test_el_default_de_umbral_y_es_1_0_leido_de_la_firma():
    """El default de `umbral_y` es 1.0, leído de la firma."""
    parametro = inspect.signature(clasificar_xyz).parameters["umbral_y"]

    assert parametro.default == 1.0
    assert parametro.default == PARAMETROS_DEFAULT["cv_confianza_media"]
    assert isinstance(parametro.default, float)
    assert not isinstance(parametro.default, bool)
    assert parametro.annotation is float


def test_sin_umbrales_equivale_a_pasar_los_defaults_de_config():
    """No pasar umbrales equivale a pasar 0.5 y 1.0: nada cambió por defecto."""
    historial = _apilados(
        {
            "P001": [100.0, 105.0, 98.0, 102.0],
            "P002": [50.0, 300.0, 80.0, 450.0],
            "P003": [10.0, 200.0, 15.0, 180.0],
        }
    )

    pd.testing.assert_frame_equal(
        clasificar_xyz(historial),
        clasificar_xyz(
            historial,
            umbral_x=PARAMETROS_DEFAULT["cv_confianza_alta"],
            umbral_y=PARAMETROS_DEFAULT["cv_confianza_media"],
        ),
    )


def test_umbral_x_custom_0_3_reclasifica_el_cv_0_4_a_clase_y():
    """CV 0.4: clase X con el default (0.5) y clase Y con umbral_x = 0.3."""
    historial = _dos_periodos_con_cv(0.4)

    por_defecto = clasificar_xyz(historial)
    custom = clasificar_xyz(historial, umbral_x=0.3)

    assert _cv(por_defecto, "P1") == pytest.approx(0.4, rel=1e-6)
    assert _clase(por_defecto, "P1") == "X"
    assert _clase(custom, "P1") == "Y"
    # El umbral solo mueve la clasificación: el CV es el mismo.
    pd.testing.assert_series_equal(custom["cv"], por_defecto["cv"])


def test_umbral_x_custom_0_1_reclasifica_el_cv_0_2_a_clase_y():
    """Estrechar el corte mueve en el otro sentido: CV 0.2 pasa de X a Y."""
    historial = _dos_periodos_con_cv(0.2)

    assert _clase(clasificar_xyz(historial), "P1") == "X"
    assert _clase(clasificar_xyz(historial, umbral_x=0.1), "P1") == "Y"


def test_umbral_y_custom_1_5_reclasifica_el_cv_1_2_a_clase_y():
    """CV 1.2: clase Z con el default (1.0) y clase Y con umbral_y = 1.5.

    La fórmula de _dos_periodos_con_cv cubre CV < sqrt(2) ~ 1.4142, así que 1.2
    sí es representable con dos periodos.
    """
    historial = _dos_periodos_con_cv(1.2)

    por_defecto = clasificar_xyz(historial)
    custom = clasificar_xyz(historial, umbral_y=1.5)

    assert _cv(por_defecto, "P1") == pytest.approx(1.2, rel=1e-6)
    assert _clase(por_defecto, "P1") == "Z"
    assert _clase(custom, "P1") == "Y"
    pd.testing.assert_series_equal(custom["cv"], por_defecto["cv"])


def test_ambos_umbrales_custom_a_la_vez_clasifican_los_tres_tramos():
    """Con 0.3 y 1.5, los CV 0.2, 0.4 y ~1.55 caen en los tres tramos.

    Con los defaults el resultado es X, X y Z: al ensanchar las bandas a
    0.3/1.5, el producto de CV 0.4 pasa a Y y el de CV ~1.55 sigue en Z.
    """
    historial = pd.concat(
        [
            _dos_periodos_con_cv(0.2, producto_id="X1"),
            _dos_periodos_con_cv(0.4, producto_id="Y1"),
            _periodos("Z1", [10.0, 300.0, 12.0]),
        ],
        ignore_index=True,
    )

    por_defecto = clasificar_xyz(historial)
    custom = clasificar_xyz(historial, umbral_x=0.3, umbral_y=1.5)

    # El tercer producto tiene un CV ~1.5546: por encima de 1.5 sigue siendo Z.
    assert _cv(custom, "Z1") == pytest.approx(
        _cv_manual([10.0, 300.0, 12.0]), rel=1e-9
    )
    assert _cv(custom, "Z1") > 1.5
    assert list(por_defecto["clase_xyz"]) == ["X", "X", "Z"]
    assert list(custom["clase_xyz"]) == ["X", "Y", "Z"]
    pd.testing.assert_series_equal(custom["cv"], por_defecto["cv"])


def test_umbrales_custom_respetan_las_fronteras_exactas():
    """Los cortes custom son inclusivos: en el CV exacto gana la clase de abajo.

    Cada frontera se construye igualando el umbral al CV del producto (calculado
    con pandas, ddof=1), así que el corte coincide con el CV que ve el motor
    salvo el redondeo de punto flotante que absorbe TOLERANCIA_CV.
    """
    cantidades_x = [100.0, 130.0, 115.0]  # CV = 15 / 115 ~ 0.1304
    cantidades_y = [50.0, 300.0, 80.0, 450.0]  # CV ~ 0.8616
    cv_x = _cv_manual(cantidades_x)
    cv_y = _cv_manual(cantidades_y)

    assert cv_x < cv_y  # el escenario tiene sentido: las bandas no se cruzan.

    resultado = clasificar_xyz(
        _apilados({"P001": cantidades_x, "P002": cantidades_y}),
        umbral_x=cv_x,
        umbral_y=cv_y,
    )

    assert _cv(resultado, "P001") == pytest.approx(cv_x, rel=1e-12)
    assert _clase(resultado, "P001") == "X"
    assert _cv(resultado, "P002") == pytest.approx(cv_y, rel=1e-12)
    assert _clase(resultado, "P002") == "Y"


def test_los_umbrales_custom_tambien_absorben_el_ruido_de_punto_flotante():
    """CV apenas por encima de 0.3: sigue siendo X con umbral_x = 0.3."""
    resultado = clasificar_xyz(
        _dos_periodos_con_cv(0.3 + TOLERANCIA_CV / 10.0), umbral_x=0.3
    )

    assert _cv(resultado, "P1") > 0.3
    assert _cv(resultado, "P1") <= 0.3 + TOLERANCIA_CV
    assert _clase(resultado, "P1") == "X"

