"""Tests unitarios del evaluador de la rúbrica de 6 criterios (MVP.md §10).

Solo se prueba la función pura ``src.evaluador.evaluar_recomendaciones``: no se
toca red, base de datos ni archivos. Los dos últimos tests cubren la parte de
E/S (``guardar_evaluaciones`` y ``evaluar_y_guardar``) con un cliente de Supabase
falso en memoria, así que tampoco salen a la red.
"""

import numpy as np
import pandas as pd
import pytest

from src.evaluador import (
    AHORRO_PCT,
    COLUMNAS_REQUERIDAS,
    COLUMNAS_SALIDA,
    CRITERIO_AHORRO,
    CRITERIO_CONFIANZA,
    CRITERIO_CONFIABILIDAD,
    CRITERIO_EFICIENCIA,
    CRITERIO_IMPORTANCIA,
    CRITERIO_RIESGO,
    CV_ALTA,
    CV_MODERADA,
    ESTADO_ACEPTABLE_CON_RESERVAS,
    ESTADO_ALTA_CONFIANZA,
    ESTADO_ATENCION,
    ESTADO_AHORRO_DETECTADO,
    ESTADO_BAJA_CONFIANZA,
    ESTADO_CONFIANZA_MODERADA,
    ESTADO_CONFIABLE,
    ESTADO_CRITICO,
    ESTADO_OPTIMA,
    ESTADO_PEDIDO_EXCESIVO,
    ESTADO_PEDIDO_PEQUENO,
    ESTADO_RIESGOSO,
    ESTADO_SIN_OPORTUNIDAD,
    ESTADO_SIN_RIESGO,
    IMPORTANCIA_ALTA,
    IMPORTANCIA_BAJA,
    IMPORTANCIA_MEDIA,
    ORDEN_CRITERIOS,
    RATIO_MAX,
    RATIO_MIN,
    SCORE_CONFIABLE,
    SCORE_RIESGOSO,
    TABLA_EVALUACIONES,
    TOLERANCIA_AHORRO,
    TOLERANCIA_CV,
    TOLERANCIA_RATIO,
    TOLERANCIA_SCORE,
    evaluar_recomendaciones,
    evaluar_y_guardar,
    guardar_evaluaciones,
)

# Columnas de la salida, escritas explícitamente para que el contrato quede
# fijado en el test y no se derive de la constante del módulo.
COLUMNAS_ESPERADAS: tuple[str, ...] = (
    "recomendacion_id",
    "criterio",
    "estado",
    "valor_numerico",
)

# Los cinco criterios numéricos: todos menos 'importancia_producto', que no tiene
# valor numérico (es la única tabla de estados categórica pura).
CRITERIOS_NUMERICOS: tuple[str, ...] = (
    CRITERIO_RIESGO,
    CRITERIO_EFICIENCIA,
    CRITERIO_CONFIANZA,
    CRITERIO_CONFIABILIDAD,
    CRITERIO_AHORRO,
)


# ---------------------------------------------------------------- utilidades


def _recomendacion(
    recomendacion_id: str = "R001",
    *,
    stock_actual: float = 120.0,
    stock_seguridad: float = 50.0,
    punto_reorden: float = 100.0,
    cantidad_recomendada: float = 100.0,
    cantidad_eoq: float = 100.0,
    cv_demanda: float = 0.25,
    clase_abc: str = "A",
    clase_xyz: str = "X",
    score_proveedor: float = 90.0,
    ahorro_neto_estimado: float = 50.0,
    costo_total_pedido: float = 1000.0,
    producto_id: str = "P001",
    extra: dict | None = None,
) -> dict:
    """Fila de recomendación con los 13 campos que espera el evaluador.

    Los defaults son el caso "todo bien": sin riesgo de quiebre (120 > 100),
    cantidad igual al EOQ (ratio 1.0), CV 0.25 (alta confianza), A/X (importancia
    alta), score 90 (confiable) y ahorro de 50 sobre un pedido de 1000 (5 %, por
    encima del 3 %).

    ``extra`` añade columnas adicionales (por ejemplo, las del recomendador) para
    comprobar que el evaluador las ignora.
    """
    fila: dict = {
        "recomendacion_id": recomendacion_id,
        "producto_id": producto_id,
        "stock_actual": stock_actual,
        "stock_seguridad": stock_seguridad,
        "punto_reorden": punto_reorden,
        "cantidad_recomendada": cantidad_recomendada,
        "cantidad_eoq": cantidad_eoq,
        "cv_demanda": cv_demanda,
        "clase_abc": clase_abc,
        "clase_xyz": clase_xyz,
        "score_proveedor": score_proveedor,
        "ahorro_neto_estimado": ahorro_neto_estimado,
        "costo_total_pedido": costo_total_pedido,
    }
    if extra is not None:
        fila.update(extra)
    return fila


def _dataframe(filas: list[dict], index: list | None = None) -> pd.DataFrame:
    """DataFrame de entrada con una fila por diccionario."""
    return pd.DataFrame(filas, index=index)


def _uno(**kwargs) -> pd.DataFrame:
    """DataFrame de una sola recomendación, para los casos de frontera."""
    return _dataframe([_recomendacion(**kwargs)])


def _vacio() -> pd.DataFrame:
    """DataFrame sin filas, pero con las 13 columnas requeridas."""
    return pd.DataFrame(
        {columna: pd.Series(dtype=object) for columna in COLUMNAS_REQUERIDAS}
    )


def _fila(
    resultado: pd.DataFrame, criterio: str, recomendacion_id: str = "R001"
) -> pd.Series:
    """Fila de la salida correspondiente a (recomendacion_id, criterio)."""
    mascara = (resultado["recomendacion_id"] == recomendacion_id) & (
        resultado["criterio"] == criterio
    )
    return resultado[mascara].iloc[0]


def _estado(resultado: pd.DataFrame, criterio: str, recomendacion_id: str = "R001"):
    """estado del criterio indicado (puede ser cualquiera de los seis)."""
    return _fila(resultado, criterio, recomendacion_id)["estado"]


def _valor(resultado: pd.DataFrame, criterio: str, recomendacion_id: str = "R001"):
    """valor_numerico del criterio indicado, tal cual (puede ser None)."""
    return _fila(resultado, criterio, recomendacion_id)["valor_numerico"]


class _ClienteFalso:
    """Cliente de Supabase mínimo, en memoria: registra lo que se le pide."""

    def __init__(self) -> None:
        self.tablas: list[str] = []
        self.insertados: list[dict] | None = None
        self.ejecutado: bool = False

    def table(self, nombre: str) -> "_TablaFalsa":
        """Guarda el nombre de la tabla consultada y devuelve el constructor."""
        self.tablas.append(nombre)
        return _TablaFalsa(self)


class _TablaFalsa:
    """Constructor de consultas mínimo: solo ``insert(...).execute()``."""

    def __init__(self, cliente: _ClienteFalso) -> None:
        self._cliente = cliente

    def insert(self, registros: list[dict]) -> "_TablaFalsa":
        """Guarda los registros que se quieren insertar."""
        self._cliente.insertados = registros
        return self

    def execute(self) -> "_TablaFalsa":
        """Marca que la petición se ejecutó."""
        self._cliente.ejecutado = True
        return self


# -------------------------------------------------------- constantes del módulo


def test_las_constantes_del_modulo_son_las_esperadas():
    """Criterios, umbrales, tolerancias, etiquetas y columnas quedan fijados."""
    assert ORDEN_CRITERIOS == [
        "riesgo_quiebre_stock",
        "eficiencia_cantidad_eoq",
        "confianza_demanda",
        "importancia_producto",
        "confiabilidad_proveedor",
        "oportunidad_ahorro",
    ]
    assert (RATIO_MIN, RATIO_MAX) == (0.90, 1.10)
    assert (CV_ALTA, CV_MODERADA) == (0.5, 1.0)
    assert (SCORE_CONFIABLE, SCORE_RIESGOSO) == (80.0, 60.0)
    assert AHORRO_PCT == 0.03
    assert (
        TOLERANCIA_RATIO,
        TOLERANCIA_CV,
        TOLERANCIA_SCORE,
        TOLERANCIA_AHORRO,
    ) == (1e-9, 1e-9, 1e-9, 1e-9)
    assert COLUMNAS_REQUERIDAS == (
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
    assert COLUMNAS_SALIDA == (
        "recomendacion_id",
        "criterio",
        "estado",
        "valor_numerico",
    )
    assert TABLA_EVALUACIONES == "evaluaciones_criterios"
    assert (ESTADO_CRITICO, ESTADO_ATENCION, ESTADO_SIN_RIESGO) == (
        "Crítico",
        "Atención",
        "Sin riesgo",
    )
    assert (ESTADO_PEDIDO_PEQUENO, ESTADO_OPTIMA, ESTADO_PEDIDO_EXCESIVO) == (
        "Pedido muy pequeño",
        "Óptima",
        "Pedido excesivo",
    )
    assert (
        ESTADO_ALTA_CONFIANZA,
        ESTADO_CONFIANZA_MODERADA,
        ESTADO_BAJA_CONFIANZA,
    ) == (
        "Alta confianza",
        "Confianza moderada",
        "Baja confianza (revisión manual)",
    )
    assert (IMPORTANCIA_ALTA, IMPORTANCIA_MEDIA, IMPORTANCIA_BAJA) == (
        "Alta",
        "Media",
        "Baja",
    )
    assert (
        ESTADO_CONFIABLE,
        ESTADO_ACEPTABLE_CON_RESERVAS,
        ESTADO_RIESGOSO,
    ) == ("Confiable", "Aceptable con reservas", "Riesgoso")
    assert (ESTADO_AHORRO_DETECTADO, ESTADO_SIN_OPORTUNIDAD) == (
        "Ahorro detectado",
        "Sin oportunidad adicional",
    )


# ------------------------------------------------------------- caso principal

# Estado del criterio 1 esperado para cada recomendación de
# ``test_genera_seis_filas_por_recomendacion_y_evalua_cada_una_por_separado``:
# la segunda recomendación recibe un stock_actual por debajo del stock de
# seguridad, para comprobar que cada fila se evalúa con sus propios datos.
ESTADOS_DE_RIESGO_POR_RECOMENDACION: dict[int, str] = {
    1: ESTADO_SIN_RIESGO,
    2: ESTADO_CRITICO,
    3: ESTADO_SIN_RIESGO,
}


@pytest.mark.parametrize("cantidad", [1, 3])
def test_genera_seis_filas_por_recomendacion_y_evalua_cada_una_por_separado(
    cantidad: int,
):
    """1 recomendación -> 6 filas; 3 recomendaciones -> 18 filas (6 cada una).

    Además, los estados de cada recomendación salen de sus propios datos: la
    segunda trae stock_actual por debajo del stock de seguridad y queda
    "Crítico" aunque las otras no.
    """
    filas: list[dict] = [
        _recomendacion(
            f"R{indice:03d}",
            stock_actual=10.0 if indice == 2 else 120.0,
        )
        for indice in range(1, cantidad + 1)
    ]

    resultado = evaluar_recomendaciones(_dataframe(filas))

    assert len(resultado) == 6 * cantidad
    assert resultado["recomendacion_id"].value_counts().to_dict() == {
        f"R{indice:03d}": 6 for indice in range(1, cantidad + 1)
    }
    for indice in range(1, cantidad + 1):
        recomendacion_id = f"R{indice:03d}"
        criterios = resultado.loc[
            resultado["recomendacion_id"] == recomendacion_id, "criterio"
        ].astype(str)
        assert criterios.value_counts().to_dict() == {
            criterio: 1 for criterio in ORDEN_CRITERIOS
        }
        assert (
            _estado(resultado, CRITERIO_RIESGO, recomendacion_id)
            == ESTADOS_DE_RIESGO_POR_RECOMENDACION[indice]
        )


def test_la_salida_tiene_las_columnas_esperadas_y_el_criterio_categorico_ordenado():
    """Las cuatro columnas, la categórica ordenada y un RangeIndex desde 0."""
    resultado = evaluar_recomendaciones(_uno())

    assert list(resultado.columns) == list(COLUMNAS_ESPERADAS)
    assert isinstance(resultado["criterio"].dtype, pd.CategoricalDtype)
    assert resultado["criterio"].cat.ordered
    assert list(resultado["criterio"].cat.categories) == ORDEN_CRITERIOS
    assert list(resultado.index) == list(range(6))



# ------------------------------------ criterio 1: riesgo de quiebre de stock


@pytest.mark.parametrize(
    "stock_actual, estado",
    [
        (30.0, ESTADO_CRITICO),
        (50.0, ESTADO_CRITICO),  # frontera: stock_actual == stock_seguridad
        (80.0, ESTADO_ATENCION),
        (100.0, ESTADO_ATENCION),  # frontera: stock_actual == punto_reorden
        (100.5, ESTADO_SIN_RIESGO),
    ],
)
def test_criterio_de_riesgo_en_sus_tres_estados_y_en_las_fronteras(
    stock_actual: float, estado: str
):
    """Con stock_seguridad = 50 y punto_reorden = 100 en todos los casos."""
    resultado = evaluar_recomendaciones(_uno(stock_actual=stock_actual))

    assert _estado(resultado, CRITERIO_RIESGO) == estado
    assert _valor(resultado, CRITERIO_RIESGO) == stock_actual


# ----------------------------------- criterio 2: eficiencia de la cantidad


@pytest.mark.parametrize(
    "cantidad_recomendada, cantidad_eoq, estado",
    [
        (50.0, 100.0, ESTADO_PEDIDO_PEQUENO),
        (100.0, 100.0, ESTADO_OPTIMA),
        (150.0, 100.0, ESTADO_PEDIDO_EXCESIVO),
    ],
)
def test_criterio_de_eficiencia_en_sus_tres_estados(
    cantidad_recomendada: float, cantidad_eoq: float, estado: str
):
    """El ratio se calcula como cantidad_recomendada / cantidad_eoq."""
    resultado = evaluar_recomendaciones(
        _uno(cantidad_recomendada=cantidad_recomendada, cantidad_eoq=cantidad_eoq)
    )

    assert _estado(resultado, CRITERIO_EFICIENCIA) == estado
    assert _valor(resultado, CRITERIO_EFICIENCIA) == pytest.approx(
        cantidad_recomendada / cantidad_eoq
    )


@pytest.mark.parametrize("ratio_objetivo", [RATIO_MIN, RATIO_MAX])
def test_criterio_de_eficiencia_en_las_fronteras_del_rango_optimo(
    ratio_objetivo: float,
):
    """Un ratio exactamente 0.90 o 1.10 es "Óptima", no "muy pequeño"/"excesivo".

    Con cantidad_eoq = 1.0 la división es exacta, así que el ratio que calcula el
    módulo es el mismo double que el umbral.
    """
    resultado = evaluar_recomendaciones(
        _uno(cantidad_recomendada=ratio_objetivo, cantidad_eoq=1.0)
    )

    assert _valor(resultado, CRITERIO_EFICIENCIA) == ratio_objetivo
    assert _estado(resultado, CRITERIO_EFICIENCIA) == ESTADO_OPTIMA


@pytest.mark.parametrize(
    "ratio_objetivo, umbral",
    [
        (RATIO_MIN - TOLERANCIA_RATIO / 10.0, RATIO_MIN),
        (RATIO_MAX + TOLERANCIA_RATIO / 10.0, RATIO_MAX),
    ],
)
def test_criterio_de_eficiencia_con_ruido_dentro_de_la_tolerancia_es_optima(
    ratio_objetivo: float, umbral: float
):
    """El ruido de punto flotante en el corte no debe degradar el estado."""
    resultado = evaluar_recomendaciones(
        _uno(cantidad_recomendada=ratio_objetivo, cantidad_eoq=1.0)
    )
    ratio = _valor(resultado, CRITERIO_EFICIENCIA)

    # El ratio quedó del lado "malo" del umbral, pero a menos de una tolerancia.
    assert ratio != umbral
    assert abs(ratio - umbral) <= TOLERANCIA_RATIO
    assert _estado(resultado, CRITERIO_EFICIENCIA) == ESTADO_OPTIMA


# ------------------------------------- criterio 3: confianza en la demanda


@pytest.mark.parametrize(
    "cv_demanda, estado",
    [
        (0.25, ESTADO_ALTA_CONFIANZA),
        (0.75, ESTADO_CONFIANZA_MODERADA),
        (1.5, ESTADO_BAJA_CONFIANZA),
    ],
)
def test_criterio_de_confianza_en_sus_tres_estados(cv_demanda: float, estado: str):
    resultado = evaluar_recomendaciones(_uno(cv_demanda=cv_demanda))

    assert _estado(resultado, CRITERIO_CONFIANZA) == estado
    assert _valor(resultado, CRITERIO_CONFIANZA) == cv_demanda


@pytest.mark.parametrize(
    "cv_demanda, estado",
    [
        (CV_ALTA, ESTADO_ALTA_CONFIANZA),
        (CV_MODERADA, ESTADO_CONFIANZA_MODERADA),
    ],
)
def test_criterio_de_confianza_en_las_fronteras(cv_demanda: float, estado: str):
    """Un CV de 0.5 sigue siendo alta confianza y uno de 1.0, moderada."""
    resultado = evaluar_recomendaciones(_uno(cv_demanda=cv_demanda))

    assert _estado(resultado, CRITERIO_CONFIANZA) == estado



# -------------------------------- criterio 4: importancia del producto ABC x XYZ


@pytest.mark.parametrize(
    "clase_abc, clase_xyz, estado",
    [
        ("A", "X", IMPORTANCIA_ALTA),
        ("A", "Y", IMPORTANCIA_ALTA),
        ("A", "Z", IMPORTANCIA_MEDIA),
        ("B", "X", IMPORTANCIA_ALTA),
        ("B", "Y", IMPORTANCIA_MEDIA),
        ("B", "Z", IMPORTANCIA_MEDIA),
        ("C", "X", IMPORTANCIA_MEDIA),
        ("C", "Y", IMPORTANCIA_BAJA),
        ("C", "Z", IMPORTANCIA_BAJA),
    ],
)
def test_criterio_de_importancia_en_las_nueve_combinaciones_abc_xyz(
    clase_abc: str, clase_xyz: str, estado: str
):
    """Las nueve celdas de la tabla de doble entrada de MVP.md §10."""
    resultado = evaluar_recomendaciones(
        _uno(clase_abc=clase_abc, clase_xyz=clase_xyz)
    )

    assert _estado(resultado, CRITERIO_IMPORTANCIA) == estado


def test_criterio_de_importancia_tiene_valor_numerico_none():
    """El único criterio categórico puro no tiene valor numérico asociado."""
    resultado = evaluar_recomendaciones(_uno())

    assert _valor(resultado, CRITERIO_IMPORTANCIA) is None
    # La columna es object (mezcla float con None) y el único nulo es el del
    # criterio 4.
    assert resultado["valor_numerico"].dtype == object
    assert resultado["valor_numerico"].isna().sum() == 1
    assert resultado.loc[
        resultado["criterio"] == CRITERIO_IMPORTANCIA, "valor_numerico"
    ].isna().all()


@pytest.mark.parametrize(
    "clase_abc, clase_xyz",
    [("D", "X"), ("A", "W")],
)
def test_criterio_de_importancia_con_una_clase_fuera_de_tabla_lanza_value_error(
    clase_abc: str, clase_xyz: str
):
    """estado es not null en la base: un dato fuera de contrato se reporta."""
    with pytest.raises(ValueError) as error:
        evaluar_recomendaciones(_uno(clase_abc=clase_abc, clase_xyz=clase_xyz))

    assert "importancia_producto" in str(error.value)
    assert repr(clase_abc) in str(error.value)
    assert repr(clase_xyz) in str(error.value)


# ------------------------------------ criterio 5: confiabilidad del proveedor


@pytest.mark.parametrize(
    "score_proveedor, estado",
    [
        (95.0, ESTADO_CONFIABLE),
        (70.0, ESTADO_ACEPTABLE_CON_RESERVAS),
        (45.0, ESTADO_RIESGOSO),
    ],
)
def test_criterio_de_confiabilidad_en_sus_tres_estados(
    score_proveedor: float, estado: str
):
    resultado = evaluar_recomendaciones(_uno(score_proveedor=score_proveedor))

    assert _estado(resultado, CRITERIO_CONFIABILIDAD) == estado
    assert _valor(resultado, CRITERIO_CONFIABILIDAD) == score_proveedor


@pytest.mark.parametrize(
    "score_proveedor, estado",
    [
        (SCORE_CONFIABLE, ESTADO_CONFIABLE),
        (SCORE_RIESGOSO, ESTADO_ACEPTABLE_CON_RESERVAS),
    ],
)
def test_criterio_de_confiabilidad_en_las_fronteras_de_80_y_60(
    score_proveedor: float, estado: str
):
    """Un score de 80 es confiable y uno de 60, aceptable con reservas."""
    resultado = evaluar_recomendaciones(_uno(score_proveedor=score_proveedor))

    assert _estado(resultado, CRITERIO_CONFIABILIDAD) == estado


# ---------------------------------------- criterio 6: oportunidad de ahorro


@pytest.mark.parametrize(
    "ahorro_neto_estimado, estado",
    [
        (45.0, ESTADO_AHORRO_DETECTADO),
        (12.0, ESTADO_SIN_OPORTUNIDAD),
    ],
)
def test_criterio_de_ahorro_en_sus_dos_estados(
    ahorro_neto_estimado: float, estado: str
):
    """El umbral es el 3 % de un pedido de 1000, es decir 30."""
    resultado = evaluar_recomendaciones(
        _uno(ahorro_neto_estimado=ahorro_neto_estimado, costo_total_pedido=1000.0)
    )

    assert _estado(resultado, CRITERIO_AHORRO) == estado
    assert _valor(resultado, CRITERIO_AHORRO) == ahorro_neto_estimado


@pytest.mark.parametrize("descuento_de_tolerancia", [0.0, TOLERANCIA_AHORRO / 10.0])
def test_criterio_de_ahorro_en_la_frontera_exacta_del_tres_por_ciento(
    descuento_de_tolerancia: float,
):
    """Un ahorro exactamente igual al 3 % del pedido es "Ahorro detectado".

    El segundo caso resta una fracción de la tolerancia al umbral, para
    comprobar que el ruido de punto flotante justo por debajo del corte no
    cambia el estado.
    """
    umbral = 1000.0 * AHORRO_PCT
    ahorro = umbral - descuento_de_tolerancia

    resultado = evaluar_recomendaciones(
        _uno(ahorro_neto_estimado=ahorro, costo_total_pedido=1000.0)
    )

    assert umbral - _valor(resultado, CRITERIO_AHORRO) <= TOLERANCIA_AHORRO
    assert _estado(resultado, CRITERIO_AHORRO) == ESTADO_AHORRO_DETECTADO



# --------------------------------------------------------- valor_numerico


def test_valor_numerico_de_los_cinco_criterios_numericos():
    """Cada criterio numérico trae su valor, como float de Python."""
    resultado = evaluar_recomendaciones(
        _uno(
            stock_actual=77.5,
            cantidad_recomendada=45.0,
            cantidad_eoq=50.0,
            cv_demanda=0.75,
            score_proveedor=72.5,
            ahorro_neto_estimado=8.25,
            costo_total_pedido=1000.0,
        )
    )

    assert _valor(resultado, CRITERIO_RIESGO) == 77.5
    assert _valor(resultado, CRITERIO_EFICIENCIA) == 0.9
    assert _valor(resultado, CRITERIO_CONFIANZA) == 0.75
    assert _valor(resultado, CRITERIO_CONFIABILIDAD) == 72.5
    assert _valor(resultado, CRITERIO_AHORRO) == 8.25
    for criterio in CRITERIOS_NUMERICOS:
        assert isinstance(_valor(resultado, criterio), float)


# ------------------------------------------------------------ casos borde


@pytest.mark.parametrize("columna", COLUMNAS_REQUERIDAS)
def test_falta_una_columna_lanza_value_error(columna: str):
    """La validación de columnas es estricta y nombra lo que falta."""
    entrada = _uno().drop(columns=[columna])

    with pytest.raises(ValueError) as error:
        evaluar_recomendaciones(entrada)

    assert "evaluar_recomendaciones requiere las columnas" in str(error.value)
    assert columna in str(error.value)


def test_dataframe_vacio_con_las_columnas_devuelve_salida_vacia():
    """Sin filas se devuelve vacío, pero con el mismo contrato de columnas."""
    resultado = evaluar_recomendaciones(_vacio())

    assert resultado.empty
    assert list(resultado.columns) == list(COLUMNAS_ESPERADAS)
    assert isinstance(resultado["criterio"].dtype, pd.CategoricalDtype)
    assert list(resultado["criterio"].cat.categories) == ORDEN_CRITERIOS
    assert resultado["valor_numerico"].dtype == object
    assert list(resultado.index) == []


def test_dataframe_vacio_sin_columnas_lanza_value_error():
    """La validación ocurre siempre: también sin filas y sin columnas."""
    with pytest.raises(ValueError) as error:
        evaluar_recomendaciones(pd.DataFrame())

    assert "faltan: recomendacion_id" in str(error.value)

    with pytest.raises(ValueError) as error:
        evaluar_recomendaciones(_vacio().drop(columns=["costo_total_pedido"]))

    assert "faltan: costo_total_pedido" in str(error.value)


def test_no_modifica_el_dataframe_de_entrada():
    """La función es pura: la entrada queda igual, con su índice y columnas."""
    entrada = _dataframe(
        [
            _recomendacion("R001"),
            _recomendacion("R002", stock_actual=10.0, clase_abc="C"),
        ],
        index=[10, 20],
    )
    copia = entrada.copy(deep=True)

    evaluar_recomendaciones(entrada)

    pd.testing.assert_frame_equal(entrada, copia)
    assert list(entrada.index) == [10, 20]
    assert list(entrada.columns) == list(COLUMNAS_REQUERIDAS)


def test_la_salida_esta_ordenada_por_recomendacion_id_y_criterio():
    """Orden por (recomendacion_id, criterio) con el orden lógico de la rúbrica.

    El orden de los criterios no es alfabético: seguiría el de
    ORDEN_CRITERIOS. Las columnas extra del recomendador se ignoran y el índice
    de la salida se normaliza a 0..N-1.
    """
    entrada = _dataframe(
        [
            _recomendacion("R003", extra={"nombre": "Tres", "urgencia": "Crítico"}),
            _recomendacion("R001", extra={"nombre": "Uno", "urgencia": "Atención"}),
            _recomendacion("R002", extra={"nombre": "Dos", "urgencia": "Sin riesgo"}),
        ],
        index=[10, 20, 30],
    )

    resultado = evaluar_recomendaciones(entrada)

    esperado = [
        (recomendacion_id, criterio)
        for recomendacion_id in ["R001", "R002", "R003"]
        for criterio in ORDEN_CRITERIOS
    ]
    obtenido = list(
        zip(resultado["recomendacion_id"], resultado["criterio"].astype(str))
    )
    assert obtenido == esperado
    assert list(resultado.columns) == list(COLUMNAS_ESPERADAS)
    assert list(resultado.index) == list(range(18))



# ------------------------------------------------------------------ E/S


def test_guardar_evaluaciones_no_inserta_nada_si_no_hay_filas():
    """Un DataFrame sin filas no genera ninguna petición a Supabase."""
    cliente = _ClienteFalso()

    guardar_evaluaciones(cliente, evaluar_recomendaciones(_vacio()))

    assert cliente.tablas == []
    assert cliente.insertados is None
    assert not cliente.ejecutado


def test_guardar_evaluaciones_convierte_nan_y_escalares_de_numpy_a_nativos():
    """NaN se escribe como None y los escalares de numpy, como nativos.

    Se construye el DataFrame a mano porque es la única forma de meter un NaN en
    ``valor_numerico`` (la función pura escribe None o un float) y un np.int64 en
    ``recomendacion_id``: el cliente de Supabase serializa con el módulo json
    estándar, que no acepta esos tipos.
    """
    cliente = _ClienteFalso()
    evaluaciones = pd.DataFrame(
        {
            "recomendacion_id": [np.int64(7)],
            "criterio": [CRITERIO_IMPORTANCIA],
            "estado": [IMPORTANCIA_ALTA],
            "valor_numerico": [np.nan],
        }
    )

    guardar_evaluaciones(cliente, evaluaciones)

    assert cliente.tablas == [TABLA_EVALUACIONES]
    assert cliente.ejecutado
    assert cliente.insertados is not None
    assert len(cliente.insertados) == 1
    assert cliente.insertados[0]["recomendacion_id"] == 7
    assert type(cliente.insertados[0]["recomendacion_id"]) is int
    assert cliente.insertados[0]["valor_numerico"] is None
    assert set(cliente.insertados[0]) == set(COLUMNAS_SALIDA)


def test_evaluar_y_guardar_inserta_los_seis_criterios_con_valores_nativos():
    """La conveniencia evalúa y escribe las 6 filas de la recomendación."""
    cliente = _ClienteFalso()

    evaluar_y_guardar(cliente, _uno())

    assert cliente.tablas == [TABLA_EVALUACIONES]
    assert cliente.ejecutado
    registros = cliente.insertados
    assert registros is not None
    assert len(registros) == 6
    assert all(set(registro) == set(COLUMNAS_SALIDA) for registro in registros)
    assert all(type(registro["criterio"]) is str for registro in registros)
    assert all(type(registro["estado"]) is str for registro in registros)

    por_criterio = {
        registro["criterio"]: registro["valor_numerico"] for registro in registros
    }
    assert list(por_criterio) == ORDEN_CRITERIOS
    assert por_criterio[CRITERIO_RIESGO] == 120.0
    assert type(por_criterio[CRITERIO_RIESGO]) is float
    assert por_criterio[CRITERIO_IMPORTANCIA] is None

