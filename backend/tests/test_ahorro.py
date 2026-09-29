"""Tests unitarios del ahorro por descuento de volumen (motor OR).

Solo pruebas de la función pura ``src.motor.ahorro.calcular_ahorro``: no se toca
red, base de datos ni archivos.

El umbral de decisión ya no es una constante del módulo
(``UMBRAL_AHORRO_PCT_DEFAULT`` se eliminó al parametrizar el módulo en la fase
4): los tests lo leen de la firma de ``calcular_ahorro``, que a su vez lo lee de
:data:`src.config.PARAMETROS_DEFAULT`.
"""

import inspect

import pandas as pd
import pytest

from src.config import PARAMETROS_DEFAULT
from src.motor.ahorro import (
    COLUMNAS_REQUERIDAS,
    ESTADO_AHORRO,
    ESTADO_SIN_OPORTUNIDAD,
    PERIODOS_POR_AÑO_DEFAULT,
    TOLERANCIA_AHORRO,
    calcular_ahorro,
)

# Umbral por defecto del motor, leído de la propia firma: los tests de fronteras
# se refieren así al default real que usa calcular_ahorro y no a una copia local
# del valor (mismo criterio que test_xyz.py, test_demanda.py y test_proveedor.py).
_FIRMA = inspect.signature(calcular_ahorro).parameters
UMBRAL_AHORRO_PCT_DEFAULT: float = _FIRMA["umbral_ahorro_pct"].default


# ---------------------------------------------------------------- utilidades


def _productos(
    producto_id: list,
    precio_unitario: list,
    cantidad_umbral_descuento: list,
    descuento_pct: list,
    cantidad_eoq: list,
    costo_unitario: list,
    costo_mantener_pct_anual: list,
    index: list | None = None,
) -> pd.DataFrame:
    """Construye el DataFrame de entrada mínimo que espera el motor."""
    return pd.DataFrame(
        {
            "producto_id": producto_id,
            "precio_unitario": precio_unitario,
            "cantidad_umbral_descuento": cantidad_umbral_descuento,
            "descuento_pct": descuento_pct,
            "cantidad_eoq": cantidad_eoq,
            "costo_unitario": costo_unitario,
            "costo_mantener_pct_anual": costo_mantener_pct_anual,
        },
        index=index,
    )


def _uno(
    precio_unitario: float,
    cantidad_eoq: float,
    cantidad_umbral_descuento: float | None,
    descuento_pct: float | None,
    costo_unitario: float,
    costo_mantener_pct_anual: float,
    producto_id: str = "P001",
) -> pd.DataFrame:
    """DataFrame de una sola fila, para los casos de frontera."""
    return _productos(
        [producto_id],
        [precio_unitario],
        [cantidad_umbral_descuento],
        [descuento_pct],
        [cantidad_eoq],
        [costo_unitario],
        [costo_mantener_pct_anual],
    )


# Los tres casos del enunciado, verificados con calculadora, más `_P004`
# (descuento declarado del 0 %, que sube el pedido y solo paga el costo extra).
# Se reutilizan en varios tests para que una fila `P001` signifique siempre lo
# mismo.
_P001: dict = {
    "precio_unitario": 24.50,
    "cantidad_umbral_descuento": 500.0,
    "descuento_pct": 5.0,
    "cantidad_eoq": 200.0,
    "costo_unitario": 25.00,
    "costo_mantener_pct_anual": 20.0,
}
_P002: dict = {
    "precio_unitario": 17.50,
    "cantidad_umbral_descuento": 300.0,
    "descuento_pct": 3.0,
    "cantidad_eoq": 600.0,
    "costo_unitario": 18.00,
    "costo_mantener_pct_anual": 20.0,
}
_P003: dict = {
    "precio_unitario": 6.20,
    "cantidad_umbral_descuento": None,
    "descuento_pct": None,
    "cantidad_eoq": 150.0,
    "costo_unitario": 6.50,
    "costo_mantener_pct_anual": 25.0,
}
_P004: dict = {
    "precio_unitario": 10.0,
    "cantidad_umbral_descuento": 500.0,
    "descuento_pct": 0.0,
    "cantidad_eoq": 200.0,
    "costo_unitario": 10.0,
    "costo_mantener_pct_anual": 20.0,
}


def _con_casos(ids: list, casos: list[dict], index: list | None = None) -> pd.DataFrame:
    """DataFrame con una fila por caso del enunciado, en el orden indicado."""
    return _productos(
        producto_id=list(ids),
        precio_unitario=[caso["precio_unitario"] for caso in casos],
        cantidad_umbral_descuento=[
            caso["cantidad_umbral_descuento"] for caso in casos
        ],
        descuento_pct=[caso["descuento_pct"] for caso in casos],
        cantidad_eoq=[caso["cantidad_eoq"] for caso in casos],
        costo_unitario=[caso["costo_unitario"] for caso in casos],
        costo_mantener_pct_anual=[
            caso["costo_mantener_pct_anual"] for caso in casos
        ],
        index=index,
    )


def _por_producto(resultado: pd.DataFrame) -> pd.DataFrame:
    """Vista indexada por producto_id, para consultar sin depender del orden."""
    return resultado.set_index("producto_id")


def _valor(resultado: pd.DataFrame, producto_id: str, columna: str) -> float:
    """Valor numérico de una columna para el producto indicado."""
    return float(_por_producto(resultado).loc[producto_id, columna])


def _estado(resultado: pd.DataFrame, producto_id: str) -> str:
    """estado del producto indicado."""
    return _por_producto(resultado).loc[producto_id, "estado"]


def _mapa_estados(resultado: pd.DataFrame) -> dict:
    """Devuelve {producto_id: estado}, sin depender del orden de las filas."""
    return dict(zip(resultado["producto_id"], resultado["estado"]))


# -------------------------------------------------------- constantes del módulo


def test_las_constantes_del_modulo_son_las_esperadas():
    """Umbral (de la firma), periodos, tolerancia, columnas y etiquetas, fijos."""
    assert UMBRAL_AHORRO_PCT_DEFAULT == 3.0
    assert PERIODOS_POR_AÑO_DEFAULT == 12
    assert TOLERANCIA_AHORRO == 1e-9
    assert COLUMNAS_REQUERIDAS == (
        "producto_id",
        "precio_unitario",
        "cantidad_umbral_descuento",
        "descuento_pct",
        "cantidad_eoq",
        "costo_unitario",
        "costo_mantener_pct_anual",
    )
    assert (ESTADO_AHORRO, ESTADO_SIN_OPORTUNIDAD) == (
        "Ahorro detectado",
        "Sin oportunidad adicional",
    )


# ------------------------------------------------------------ caso principal


def test_caso_normal_p001_del_ejemplo():
    """EOQ 200 < umbral 500: se sube el pedido y el descuento paga el exceso.

    cantidad_pedido = 500; cantidad_extra = 300
    ahorro_bruto = 500 * 24.50 * 0.05 = 612.50
    costo_extra_mantener = 300 * 25.00 * 0.20 / 12 = 125.00  (un periodo)
    ahorro_neto = 487.50; umbral_ahorro = 12250.00 * 0.03 = 367.50 -> detectado
    """
    resultado = calcular_ahorro(_con_casos(["P001"], [_P001]))

    assert list(resultado.columns) == [
        "producto_id",
        "cantidad_pedido",
        "ahorro_bruto",
        "costo_extra_mantener",
        "ahorro_neto",
        "estado",
    ]
    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(612.50)
    assert _valor(resultado, "P001", "costo_extra_mantener") == pytest.approx(125.00)
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(487.50)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_caso_normal_p002_del_ejemplo():
    """EOQ 600 >= umbral 300: el descuento se cobra sin inventario adicional.

    cantidad_pedido = 600; cantidad_extra = 0
    ahorro_bruto = 600 * 17.50 * 0.03 = 315.00
    costo_extra_mantener = 0; ahorro_neto = 315.00
    umbral_ahorro = 10500.00 * 0.03 = 315.00 -> frontera exacta
    """
    resultado = calcular_ahorro(_con_casos(["P002"], [_P002]))

    assert _valor(resultado, "P002", "cantidad_pedido") == pytest.approx(600.0)
    assert _valor(resultado, "P002", "ahorro_bruto") == pytest.approx(315.00)
    assert _valor(resultado, "P002", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P002", "ahorro_neto") == pytest.approx(315.00)
    assert _estado(resultado, "P002") == ESTADO_AHORRO


def test_caso_normal_p003_sin_descuento_del_ejemplo():
    """Umbral y descuento nulos: el pedido se queda en el EOQ y no hay ahorro."""
    resultado = calcular_ahorro(_con_casos(["P003"], [_P003]))

    assert _valor(resultado, "P003", "cantidad_pedido") == pytest.approx(150.0)
    assert _valor(resultado, "P003", "ahorro_bruto") == 0.0
    assert _valor(resultado, "P003", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P003", "ahorro_neto") == 0.0
    assert _estado(resultado, "P003") == ESTADO_SIN_OPORTUNIDAD


def test_lote_mixto_con_los_tres_casos_del_ejemplo():
    """Con y sin descuento en el mismo lote: cada producto se calcula aparte."""
    resultado = calcular_ahorro(
        _con_casos(["P001", "P002", "P003"], [_P001, _P002, _P003])
    )

    assert resultado["producto_id"].tolist() == ["P001", "P002", "P003"]
    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P002", "cantidad_pedido") == pytest.approx(600.0)
    assert _valor(resultado, "P003", "cantidad_pedido") == pytest.approx(150.0)
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(487.50)
    assert _valor(resultado, "P002", "ahorro_neto") == pytest.approx(315.00)
    assert _valor(resultado, "P003", "ahorro_neto") == 0.0
    assert _mapa_estados(resultado) == {
        "P001": ESTADO_AHORRO,
        "P002": ESTADO_AHORRO,
        "P003": ESTADO_SIN_OPORTUNIDAD,
    }


def test_acepta_columnas_de_tipo_entero():
    """Con insumos int64 el resultado es el mismo y la salida numérica float64."""
    entrada = _productos(["P001"], [24.50], [500], [5], [200], [25], [20])

    assert str(entrada["cantidad_umbral_descuento"].dtype).startswith("int")
    assert str(entrada["descuento_pct"].dtype).startswith("int")
    assert str(entrada["cantidad_eoq"].dtype).startswith("int")

    resultado = calcular_ahorro(entrada)

    assert str(resultado["cantidad_pedido"].dtype) == "float64"
    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(612.50)
    assert _valor(resultado, "P001", "costo_extra_mantener") == pytest.approx(125.00)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


# ---------------------------------------------------------------- fronteras


def test_frontera_ahorro_neto_exactamente_igual_al_umbral_es_ahorro_detectado():
    """El corte es inclusivo: ahorro_neto == umbral_ahorro es "Ahorro detectado".

    precio 1.00, EOQ 1000 = umbral (no se sube nada), descuento 3 %:
    ahorro_neto = 1000 * 1.00 * 0.03 = 30.00 = 3 % de 1000.00.
    """
    resultado = calcular_ahorro(_uno(1.0, 1000.0, 1000.0, 3.0, 1.0, 100.0))

    ahorro_neto = _valor(resultado, "P001", "ahorro_neto")
    assert ahorro_neto == 30.0
    assert ahorro_neto == 1000.0 * 1.0 * (UMBRAL_AHORRO_PCT_DEFAULT / 100.0)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_frontera_con_ruido_de_punto_flotante_dentro_de_la_tolerancia():
    """Ahorro neto matemáticamente igual al umbral pero menor en float64.

    cantidad_extra = 220000.00 * 9 * 12 / (85 * 100) = 47520/17 deja el costo
    extra exactamente en 19800.00 (las tres cuartas partes de 26400.00), así que
    el ahorro neto matemático es 26400.00 - 19800.00 = 6600.00, igual al umbral
    del 3 % de 220000.00. En float64 el neto cae unas billonésimas por debajo
    (6599.999999999996), de modo que sin TOLERANCIA_AHORRO la fila se
    clasificaría como "Sin oportunidad adicional".
    """
    resultado = calcular_ahorro(
        _uno(22.0, 7204.7058823529405, 10000.0, 12.0, 85.0, 100.0)
    )

    ahorro_neto = _valor(resultado, "P001", "ahorro_neto")
    umbral_ahorro = 10000.0 * 22.0 * (UMBRAL_AHORRO_PCT_DEFAULT / 100.0)

    assert ahorro_neto < umbral_ahorro
    assert umbral_ahorro - ahorro_neto < TOLERANCIA_AHORRO
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(26400.00)
    assert _valor(resultado, "P001", "costo_extra_mantener") == pytest.approx(19800.00)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_brecha_real_menor_que_la_tolerancia_es_ahorro_detectado():
    """Una brecha real diminuta frente al umbral queda dentro de la tolerancia.

    cantidad_umbral 1 = EOQ 0.9999999999 => cantidad_extra = 1e-10 y
    costo_extra_mantener = 1e-10 / 12 = 8.3e-12, menor que TOLERANCIA_AHORRO
    (1e-9).
    """
    resultado = calcular_ahorro(_uno(1.0, 0.9999999999, 1.0, 3.0, 1.0, 100.0))

    ahorro_neto = _valor(resultado, "P001", "ahorro_neto")
    umbral_ahorro = 1.0 * 1.0 * (UMBRAL_AHORRO_PCT_DEFAULT / 100.0)

    assert 0.0 < umbral_ahorro - ahorro_neto < TOLERANCIA_AHORRO
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_brecha_real_mayor_que_la_tolerancia_es_sin_oportunidad():
    """Una brecha real de 1e-6 frente al umbral queda fuera de la tolerancia."""
    resultado = calcular_ahorro(_uno(1.0, 0.999999, 1.0, 3.0, 1.0, 100.0))

    ahorro_neto = _valor(resultado, "P001", "ahorro_neto")
    umbral_ahorro = 1.0 * 1.0 * (UMBRAL_AHORRO_PCT_DEFAULT / 100.0)

    assert umbral_ahorro - ahorro_neto > TOLERANCIA_AHORRO
    assert _estado(resultado, "P001") == ESTADO_SIN_OPORTUNIDAD


# ----------------------------------------------------------- cantidad pedida


def test_cantidad_eoq_menor_al_umbral_sube_el_pedido_hasta_el_umbral():
    """Con EOQ por debajo del umbral se sube el pedido y se paga el exceso.

    precio 8.00, EOQ 100, umbral 250, descuento 10 %, costo 2.00, mantener 50 %:
    cantidad_extra = 150; ahorro_bruto = 250 * 8.00 * 0.10 = 200.00
    costo_extra_mantener = 150 * 2.00 * 0.50 / 12 = 12.50; ahorro_neto = 187.50
    umbral_ahorro = 2000.00 * 0.03 = 60.00 -> 187.50 >= 60.00
    """
    resultado = calcular_ahorro(_uno(8.0, 100.0, 250.0, 10.0, 2.0, 50.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(250.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(200.00)
    assert _valor(resultado, "P001", "costo_extra_mantener") == pytest.approx(12.50)
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(187.50)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_descuento_menor_al_umbral_de_decision_es_sin_oportunidad():
    """Con descuento por debajo del umbral de decisión no hay oportunidad.

    precio 10.00, EOQ 500 >= umbral 100 (no se sube nada), descuento 1 %:
    ahorro_bruto = 500 * 10.00 * 0.01 = 50.00 = ahorro_neto, pero el umbral de
    decisión es 5000.00 * 0.03 = 150.00 -> "Sin oportunidad adicional".
    """
    resultado = calcular_ahorro(_uno(10.0, 500.0, 100.0, 1.0, 5.0, 20.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(50.00)
    assert _valor(resultado, "P001", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(50.00)
    assert _estado(resultado, "P001") == ESTADO_SIN_OPORTUNIDAD


def test_cantidad_eoq_igual_al_umbral_no_genera_cantidad_extra():
    """EOQ == umbral: el pedido ya accede al descuento, sin inventario adicional."""
    resultado = calcular_ahorro(_uno(10.0, 500.0, 500.0, 6.0, 5.0, 20.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P001", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(300.00)
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(300.00)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_cantidad_eoq_mayor_al_umbral_conserva_el_eoq():
    """EOQ 900 > umbral 300: se pide el EOQ, no se baja al umbral ni se sube algo."""
    resultado = calcular_ahorro(_uno(20.0, 900.0, 300.0, 4.0, 4.0, 20.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(900.0)
    assert _valor(resultado, "P001", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(720.00)
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(720.00)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


# ----------------------------------------------- valores límite del descuento


def test_umbral_nulo_con_descuento_definido_es_sin_descuento():
    """Sin cantidad mínima no hay descuento por volumen: no se sube el pedido."""
    resultado = calcular_ahorro(_uno(10.0, 600.0, None, 5.0, 5.0, 20.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(600.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == 0.0
    assert _valor(resultado, "P001", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P001", "ahorro_neto") == 0.0
    assert _estado(resultado, "P001") == ESTADO_SIN_OPORTUNIDAD


def test_descuento_nulo_con_umbral_definido_es_sin_descuento():
    """Un umbral sin descuento no da acceso a nada: el pedido se queda en el EOQ."""
    resultado = calcular_ahorro(_uno(10.0, 20.0, 100.0, None, 5.0, 20.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(20.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == 0.0
    assert _valor(resultado, "P001", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P001", "ahorro_neto") == 0.0
    assert _estado(resultado, "P001") == ESTADO_SIN_OPORTUNIDAD


def test_umbral_y_descuento_nulos_es_sin_descuento():
    """Los dos nulos juntos tampoco son un error: se trata como sin descuento."""
    resultado = calcular_ahorro(_uno(3.0, 80.0, None, None, 3.20, 15.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(80.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == 0.0
    assert _valor(resultado, "P001", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P001", "ahorro_neto") == 0.0
    assert _estado(resultado, "P001") == ESTADO_SIN_OPORTUNIDAD


def test_descuento_pct_cero_no_genera_ahorro_bruto():
    """Un descuento declarado del 0 % sube el pedido y no ahorra nada.

    El umbral y el descuento están definidos, así que el producto cuenta como
    "con descuento por volumen" y el pedido sube al umbral (así lo fija la
    regla); el ahorro bruto es 0 y el costo extra se paga completo:
    cantidad_extra = 300; costo_extra_mantener = 300 * 10.00 * 0.20 / 12 = 50.00.
    """
    resultado = calcular_ahorro(_con_casos(["P004"], [_P004]))

    assert _valor(resultado, "P004", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P004", "ahorro_bruto") == 0.0
    assert _valor(resultado, "P004", "costo_extra_mantener") == pytest.approx(50.00)
    assert _valor(resultado, "P004", "ahorro_neto") == pytest.approx(-50.00)
    assert _estado(resultado, "P004") == ESTADO_SIN_OPORTUNIDAD


def test_descuento_pct_cien_ahorra_todo_el_costo_del_pedido():
    """Un descuento del 100 % deja el ahorro bruto igual al costo del pedido."""
    resultado = calcular_ahorro(_uno(10.0, 200.0, 500.0, 100.0, 10.0, 20.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(500.0 * 10.0)
    assert _valor(resultado, "P001", "costo_extra_mantener") == pytest.approx(50.00)
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(4950.00)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_costo_mantener_cero_no_genera_costo_extra():
    """Sin costo de mantener, subir el pedido al umbral es gratis."""
    resultado = calcular_ahorro(_uno(10.0, 200.0, 500.0, 5.0, 10.0, 0.0))

    assert _valor(resultado, "P001", "cantidad_pedido") == pytest.approx(500.0)
    assert _valor(resultado, "P001", "costo_extra_mantener") == 0.0
    assert _valor(resultado, "P001", "ahorro_bruto") == pytest.approx(250.00)
    assert _valor(resultado, "P001", "ahorro_neto") == pytest.approx(250.00)
    assert _estado(resultado, "P001") == ESTADO_AHORRO


def test_umbral_ahorro_pct_cero_clasifica_como_ahorro_todo_neto_no_negativo():
    """Con umbral 0 el criterio es "no perder dinero", no un 3 % del pedido.

    P003 (sin descuento) tiene ahorro_neto = 0 y pasa a "Ahorro detectado";
    P004 (descuento declarado del 0 %, que sube el pedido) deja ahorro_neto en
    -50.00 y sigue sin oportunidad.
    """
    datos = _con_casos(["P003", "P004"], [_P003, _P004])

    resultado = calcular_ahorro(datos, umbral_ahorro_pct=0)

    assert _valor(resultado, "P003", "ahorro_neto") == 0.0
    assert _estado(resultado, "P003") == ESTADO_AHORRO
    assert _valor(resultado, "P004", "ahorro_neto") == pytest.approx(-50.00)
    assert _estado(resultado, "P004") == ESTADO_SIN_OPORTUNIDAD

    # Con el umbral por defecto (3 %), P003 vuelve a quedar sin oportunidad.
    por_defecto = calcular_ahorro(datos)
    assert _estado(por_defecto, "P003") == ESTADO_SIN_OPORTUNIDAD
    assert _estado(por_defecto, "P004") == ESTADO_SIN_OPORTUNIDAD


# ------------------------------------------------------------- periodos por año


def test_periodos_por_año_escala_el_costo_extra():
    """El costo extra se prorratea: con 1 periodo por año es 12 veces mayor.

    P001: el exceso cuesta 300 * 25.00 * 0.20 = 1500.00 al año, 125.00 con el
    default (12 periodos). ahorro_bruto y cantidad_pedido no cambian; el ahorro
    neto sí (487.50 con 12, -887.50 con 1).
    """
    entrada = _con_casos(["P001"], [_P001])

    anual = calcular_ahorro(entrada, periodos_por_año=1)
    mensual = calcular_ahorro(entrada)
    explicito = calcular_ahorro(entrada, periodos_por_año=PERIODOS_POR_AÑO_DEFAULT)

    assert _valor(anual, "P001", "costo_extra_mantener") == pytest.approx(1500.00)
    assert _valor(mensual, "P001", "costo_extra_mantener") == pytest.approx(125.00)
    assert _valor(anual, "P001", "costo_extra_mantener") == pytest.approx(
        PERIODOS_POR_AÑO_DEFAULT * _valor(mensual, "P001", "costo_extra_mantener")
    )
    assert _valor(anual, "P001", "ahorro_bruto") == _valor(
        mensual, "P001", "ahorro_bruto"
    )
    assert _valor(anual, "P001", "cantidad_pedido") == _valor(
        mensual, "P001", "cantidad_pedido"
    )
    assert _valor(anual, "P001", "ahorro_neto") == pytest.approx(-887.50)
    assert _valor(mensual, "P001", "ahorro_neto") == pytest.approx(487.50)
    assert _estado(anual, "P001") == ESTADO_SIN_OPORTUNIDAD
    assert _estado(mensual, "P001") == ESTADO_AHORRO

    # El default es exactamente PERIODOS_POR_AÑO_DEFAULT.
    pd.testing.assert_frame_equal(mensual, explicito)


@pytest.mark.parametrize(
    "periodos_por_año",
    [0, -1, -12, 2.5, 1.5, "12", None, True, False],
)
def test_periodos_por_año_invalido_lanza_value_error(periodos_por_año):
    """Cero, negativos, no enteros y booleanos se rechazan."""
    with pytest.raises(ValueError, match="periodos_por_año"):
        calcular_ahorro(
            _con_casos(["P001"], [_P001]), periodos_por_año=periodos_por_año
        )


# ---------------------------------------------------------------- validación


@pytest.mark.parametrize(
    "umbral_ahorro_pct",
    [-1, -0.01, -3.0, "3", None, True, False, [3.0]],
)
def test_umbral_ahorro_pct_invalido_lanza_value_error(umbral_ahorro_pct):
    """Negativos, no numéricos, booleanos y colecciones se rechazan."""
    with pytest.raises(ValueError, match="umbral_ahorro_pct"):
        calcular_ahorro(_con_casos(["P001"], [_P001]), umbral_ahorro_pct)


def test_los_parametros_escalares_se_validan_antes_que_las_columnas():
    """Un escalar inválido falla primero: no depende de los datos."""
    with pytest.raises(ValueError, match="umbral_ahorro_pct"):
        calcular_ahorro(pd.DataFrame(), umbral_ahorro_pct=-1)

    with pytest.raises(ValueError, match="periodos_por_año"):
        calcular_ahorro(pd.DataFrame(), umbral_ahorro_pct=3.0, periodos_por_año=0)


def test_umbral_ahorro_pct_nan_lanza_value_error():
    """NaN se rechaza explícitamente, no se propaga al cálculo.

    NaN es un float, así que pasa la comprobación de tipo; sin este rechazo,
    todas las comparaciones con el umbral serían False y el lote entero se
    clasificaría como "Sin oportunidad adicional" en silencio.
    """
    with pytest.raises(ValueError, match="nan"):
        calcular_ahorro(_con_casos(["P001"], [_P001]), umbral_ahorro_pct=float("nan"))


def test_dataframe_vacio_con_columnas_devuelve_vacio_sin_error():
    """Sin filas se devuelven las columnas y dtypes de la salida, sin excepción."""
    resultado = calcular_ahorro(_con_casos(["P001"], [_P001]).iloc[0:0])

    assert resultado.empty
    assert list(resultado.columns) == [
        "producto_id",
        "cantidad_pedido",
        "ahorro_bruto",
        "costo_extra_mantener",
        "ahorro_neto",
        "estado",
    ]
    assert [str(columna.dtype) for _, columna in resultado.items()] == [
        "object",
        "float64",
        "float64",
        "float64",
        "float64",
        "object",
    ]
    assert list(resultado.index) == []


def test_dataframe_vacio_sin_columnas_lanza_value_error():
    """La validación de columnas es estricta incluso sin filas."""
    with pytest.raises(ValueError) as excinfo:
        calcular_ahorro(pd.DataFrame())

    mensaje = str(excinfo.value)
    assert "calcular_ahorro" in mensaje
    for columna in COLUMNAS_REQUERIDAS:
        assert columna in mensaje


def test_dataframe_con_filas_y_sin_columnas_lanza_value_error():
    """Con filas pero sin las columnas del contrato también falla."""
    with pytest.raises(ValueError, match="faltan"):
        calcular_ahorro(pd.DataFrame({"producto_id": ["P001", "P002"]}))


def test_falta_una_columna_lanza_value_error_con_el_nombre():
    """El mensaje nombra la columna que falta, no solo el contrato completo."""
    datos = _con_casos(["P001"], [_P001]).drop(columns=["descuento_pct"])

    with pytest.raises(ValueError, match="descuento_pct"):
        calcular_ahorro(datos)


# ------------------------------------------------------------------ contratos


def test_la_salida_esta_ordenada_por_producto_id_con_rangeindex():
    """El orden de salida no depende del orden ni del índice de entrada."""
    entrada = _con_casos(
        ["P003", "P001", "P002"], [_P003, _P001, _P002], index=[5, 2, 9]
    )

    resultado = calcular_ahorro(entrada)

    assert resultado["producto_id"].tolist() == ["P001", "P002", "P003"]
    assert list(resultado.index) == [0, 1, 2]


def test_el_orden_de_las_filas_de_entrada_no_altera_el_resultado():
    desordenado = _con_casos(["P003", "P001", "P002"], [_P003, _P001, _P002])
    ordenado = _con_casos(["P001", "P002", "P003"], [_P001, _P002, _P003])

    pd.testing.assert_frame_equal(
        calcular_ahorro(desordenado),
        calcular_ahorro(ordenado),
    )


def test_no_modifica_el_dataframe_de_entrada():
    entrada = _con_casos(["P002", "P001", "P003"], [_P002, _P001, _P003])
    copia = entrada.copy(deep=True)

    calcular_ahorro(entrada)

    pd.testing.assert_frame_equal(entrada, copia)
    assert list(entrada.columns) == list(COLUMNAS_REQUERIDAS)


def test_dtypes_de_la_salida():
    """producto_id y estado object; cantidad, ahorro y costo float64."""
    resultado = calcular_ahorro(_con_casos(["P001", "P002"], [_P001, _P002]))

    assert str(resultado["producto_id"].dtype) == "object"
    assert str(resultado["cantidad_pedido"].dtype) == "float64"
    assert str(resultado["ahorro_bruto"].dtype) == "float64"
    assert str(resultado["costo_extra_mantener"].dtype) == "float64"
    assert str(resultado["ahorro_neto"].dtype) == "float64"
    assert str(resultado["estado"].dtype) == "object"
    assert all(isinstance(valor, str) for valor in resultado["estado"])
    assert set(resultado["estado"]) <= {ESTADO_AHORRO, ESTADO_SIN_OPORTUNIDAD}


# ------------------------------------------- umbral configurable (fase 4)


def test_los_defaults_del_umbral_vienen_de_config():
    """Sin argumentos se usa el umbral de PARAMETROS_DEFAULT (3.0, en %)."""
    parametros = inspect.signature(calcular_ahorro).parameters

    assert parametros["umbral_ahorro_pct"].default == (
        PARAMETROS_DEFAULT["ahorro_neto_min_pct"]
    )
    # Y el valor de config sigue siendo el histórico del módulo.
    assert PARAMETROS_DEFAULT["ahorro_neto_min_pct"] == 3.0


def test_el_default_de_umbral_ahorro_pct_es_3_0_leido_de_la_firma():
    """El default de `umbral_ahorro_pct` es 3.0, leído de la firma."""
    parametro = inspect.signature(calcular_ahorro).parameters["umbral_ahorro_pct"]

    assert parametro.default == 3.0
    assert parametro.default == PARAMETROS_DEFAULT["ahorro_neto_min_pct"]
    assert isinstance(parametro.default, float)
    assert not isinstance(parametro.default, bool)
    assert parametro.annotation is float


def test_sin_umbral_equivale_a_pasar_el_default_de_config():
    """No pasar umbral equivale a pasar 3.0: nada cambió por defecto."""
    entrada = _con_casos(
        ["P001", "P002", "P003", "P004"], [_P001, _P002, _P003, _P004]
    )

    pd.testing.assert_frame_equal(
        calcular_ahorro(entrada),
        calcular_ahorro(
            entrada, umbral_ahorro_pct=PARAMETROS_DEFAULT["ahorro_neto_min_pct"]
        ),
    )


def test_umbral_custom_1_0_detecta_un_ahorro_del_2_pct_del_pedido():
    """Un ahorro del 2 % del pedido: sin oportunidad con 3 %, detectado con 1 %.

    precio 10.00, EOQ 600 >= umbral 300 (no se sube el pedido), descuento 2 %:
    ahorro_neto = 600 * 10.00 * 0.02 = 120.00 = 2 % de 6000.00
    con el default (3.0) -> umbral 180.00 -> 120.00 < 180.00 -> sin oportunidad
    con umbral_ahorro_pct = 1.0 -> umbral 60.00 -> 120.00 >= 60.00 -> detectado.
    """
    entrada = _uno(10.0, 600.0, 300.0, 2.0, 5.0, 20.0)

    por_defecto = calcular_ahorro(entrada)
    custom = calcular_ahorro(entrada, umbral_ahorro_pct=1.0)

    assert _valor(por_defecto, "P001", "ahorro_neto") == pytest.approx(120.00)
    assert _valor(por_defecto, "P001", "ahorro_neto") == pytest.approx(
        0.02 * 600.0 * 10.0
    )
    assert _estado(por_defecto, "P001") == ESTADO_SIN_OPORTUNIDAD
    assert _estado(custom, "P001") == ESTADO_AHORRO
    # El umbral solo mueve la clasificación: los números no cambian.
    assert _valor(custom, "P001", "ahorro_neto") == _valor(
        por_defecto, "P001", "ahorro_neto"
    )
    assert _valor(custom, "P001", "cantidad_pedido") == pytest.approx(600.0)


def test_umbral_custom_10_0_descarta_un_ahorro_del_5_pct_del_pedido():
    """Un ahorro del 5 %: detectado con 3 %, sin oportunidad con 10 %.

    precio 20.00, EOQ 400 >= umbral 200 (no se sube el pedido), descuento 5 %:
    ahorro_neto = 400 * 20.00 * 0.05 = 400.00 = 5 % de 8000.00
    con el default (3.0) -> umbral 240.00 -> 400.00 >= 240.00 -> detectado
    con umbral_ahorro_pct = 10.0 -> umbral 800.00 -> 400.00 < 800.00 -> sin
    oportunidad.
    """
    entrada = _uno(20.0, 400.0, 200.0, 5.0, 8.0, 25.0)

    por_defecto = calcular_ahorro(entrada)
    custom = calcular_ahorro(entrada, umbral_ahorro_pct=10.0)

    assert _valor(por_defecto, "P001", "ahorro_neto") == pytest.approx(400.00)
    assert _valor(por_defecto, "P001", "ahorro_neto") == pytest.approx(
        0.05 * 400.0 * 20.0
    )
    assert _estado(por_defecto, "P001") == ESTADO_AHORRO
    assert _estado(custom, "P001") == ESTADO_SIN_OPORTUNIDAD
    assert _valor(custom, "P001", "cantidad_pedido") == pytest.approx(400.0)


def test_umbral_custom_0_0_detecta_todo_ahorro_neto_no_negativo():
    """Con umbral 0 el criterio es "no perder dinero": 120.00 y 0 pasan, -50 no.

    P005 (descuento del 2 % con EOQ >= umbral: no se sube el pedido) tiene
    ahorro_neto = 120.00; P003 (sin descuento) tiene 0.00; P004 (descuento
    declarado del 0 %, que sube el pedido) tiene -50.00.
    """
    p005: dict = {
        "precio_unitario": 10.0,
        "cantidad_umbral_descuento": 300.0,
        "descuento_pct": 2.0,
        "cantidad_eoq": 600.0,
        "costo_unitario": 5.0,
        "costo_mantener_pct_anual": 20.0,
    }
    entrada = _con_casos(["P005", "P003", "P004"], [p005, _P003, _P004])

    custom = calcular_ahorro(entrada, umbral_ahorro_pct=0.0)
    por_defecto = calcular_ahorro(entrada)

    assert _mapa_estados(custom) == {
        "P003": ESTADO_AHORRO,
        "P004": ESTADO_SIN_OPORTUNIDAD,
        "P005": ESTADO_AHORRO,
    }
    assert _valor(custom, "P005", "ahorro_neto") == pytest.approx(120.00)
    assert _valor(custom, "P003", "ahorro_neto") == 0.0
    assert _valor(custom, "P004", "ahorro_neto") == pytest.approx(-50.00)

    # Con el default (3 %) el mismo lote vuelve a perder las dos oportunidades.
    assert _estado(por_defecto, "P005") == ESTADO_SIN_OPORTUNIDAD
    assert _estado(por_defecto, "P003") == ESTADO_SIN_OPORTUNIDAD


def test_umbral_custom_respeta_la_frontera_exacta_y_la_tolerancia():
    """El corte inclusivo y TOLERANCIA_AHORRO siguen aplicando con umbral custom.

    precio 10.00, EOQ 500 >= umbral 100, descuento 4 %:
    ahorro_neto = 500 * 10.00 * 0.04 = 200.00
    umbral 4.0 -> 5000.00 * 0.04 = 200.00 (frontera exacta) -> detectado
    umbral 4.0001 -> 200.005: la brecha (0.005) supera TOLERANCIA_AHORRO -> sin
    oportunidad.
    """
    entrada = _uno(10.0, 500.0, 100.0, 4.0, 5.0, 20.0)

    exacto = calcular_ahorro(entrada, umbral_ahorro_pct=4.0)
    apenas_mayor = calcular_ahorro(entrada, umbral_ahorro_pct=4.0001)

    assert _valor(exacto, "P001", "ahorro_neto") == 200.0
    assert _valor(exacto, "P001", "ahorro_neto") == 500.0 * 10.0 * (4.0 / 100.0)
    assert _estado(exacto, "P001") == ESTADO_AHORRO
    assert _valor(apenas_mayor, "P001", "ahorro_neto") == 200.0
    assert 5000.0 * (4.0001 / 100.0) - 200.0 > TOLERANCIA_AHORRO
    assert _estado(apenas_mayor, "P001") == ESTADO_SIN_OPORTUNIDAD


def test_el_umbral_se_usa_como_porcentaje_y_no_como_fraccion():
    """0.03 no equivale a 3 %: el umbral se divide entre 100 dentro de la función.

    precio 10.00, EOQ 500 >= umbral 100, descuento 1 %:
    ahorro_neto = 500 * 10.00 * 0.01 = 50.00 = 1 % de 5000.00
    con el default (3.0 = 3 %) -> umbral 150.00 -> sin oportunidad
    con 0.03 (que como fracción sería 3 %) -> umbral 1.50 -> detectado.
    """
    entrada = _uno(10.0, 500.0, 100.0, 1.0, 5.0, 20.0)

    por_defecto = calcular_ahorro(entrada)
    con_fraccion_implicita = calcular_ahorro(entrada, umbral_ahorro_pct=0.03)

    assert _valor(por_defecto, "P001", "ahorro_neto") == pytest.approx(50.00)
    assert _estado(por_defecto, "P001") == ESTADO_SIN_OPORTUNIDAD
    assert _estado(con_fraccion_implicita, "P001") == ESTADO_AHORRO

