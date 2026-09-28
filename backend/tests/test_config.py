"""Tests unitarios de los parámetros de configuración (fase 4).

Se prueban :data:`src.config.PARAMETROS_DEFAULT`, la función pura
``src.config.verificar_parametros`` y la parte de E/S
(``src.config.cargar_parametros``) con un cliente de Supabase falso en memoria:
no se toca red, base de datos ni archivos.

El último test comprueba, en un intérprete nuevo, que importar ``src.config`` no
carga el paquete ``supabase``: el módulo no debe tener efectos secundarios al
importarse.
"""

import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from src.config import (
    PARAMETROS_DEFAULT,
    TABLA_PARAMETROS,
    cargar_parametros,
    verificar_parametros,
)

# Raíz de 'backend': es el directorio desde el que corre pytest (allí 'src' es
# importable) y el que necesita el subproceso del test de importación.
RAIZ_BACKEND = Path(__file__).resolve().parents[1]

# Los 10 parámetros con sus valores, escritos aquí como literales a propósito:
# los tests comparan contra estos literales, no contra el propio módulo.
PARAMETROS_ESPERADOS: dict[str, float] = {
    "abc_clase_a_pct": 80.0,
    "abc_clase_b_pct": 95.0,
    "ahorro_neto_min_pct": 3.0,
    "cv_confianza_alta": 0.5,
    "cv_confianza_media": 1.0,
    "demanda_ventana_default": 6.0,
    "eoq_max_pct": 110.0,
    "eoq_min_pct": 90.0,
    "score_proveedor_confiable": 80.0,
    "score_proveedor_riesgoso": 60.0,
}


# ---------------------------------------------------------------- utilidades


def _filas(parametros: dict[str, object]) -> list[dict]:
    """Filas verticales tal como las devuelve la tabla (con ``descripcion``)."""
    return [
        {
            "nombre_parametro": nombre,
            "valor": valor,
            "descripcion": f"Descripción de {nombre}",
        }
        for nombre, valor in parametros.items()
    ]


def _completos(tipo: str) -> dict[str, object]:
    """Los 10 parámetros con los valores convertidos a 'int', 'Decimal' o 'str'.

    Reproduce lo que puede devolver supabase-py para una columna ``numeric``. El
    CV de confianza alta (0.5) se deja como ``float`` en el caso 'int': no tiene
    representación entera y un cliente real no lo devolvería así.
    """
    if tipo == "int":
        return {
            nombre: int(valor) if float(valor).is_integer() else valor
            for nombre, valor in PARAMETROS_ESPERADOS.items()
        }
    if tipo == "decimal":
        decimales: dict[str, object] = {
            nombre: Decimal(str(valor))
            for nombre, valor in PARAMETROS_ESPERADOS.items()
        }
        # Postgres puede devolver un 'numeric' sin decimales como Decimal("80").
        decimales["abc_clase_a_pct"] = Decimal("80")
        return decimales
    return {nombre: str(valor) for nombre, valor in PARAMETROS_ESPERADOS.items()}


class _RespuestaFalsa:
    """Respuesta mínima de PostgREST: solo el atributo ``data``."""

    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _TablaFalsa:
    """Constructor de consultas mínimo: ``select(...).execute()``."""

    def __init__(self, cliente: "_ClienteFalso", nombre: str) -> None:
        self._cliente = cliente
        self._nombre = nombre
        self._columnas: str | None = None

    def select(self, columnas: str) -> "_TablaFalsa":
        """Guarda las columnas pedidas y devuelve el propio constructor."""
        self._columnas = columnas
        return self

    def execute(self) -> _RespuestaFalsa:
        """Registra la consulta, lanza el error configurado o devuelve los datos."""
        self._cliente.consultas.append((self._nombre, self._columnas))
        if self._cliente.error is not None:
            raise self._cliente.error
        return _RespuestaFalsa(self._cliente.data)


class _ClienteFalso:
    """Cliente de Supabase mínimo, en memoria: no sale a la red."""

    def __init__(
        self,
        data: list[dict] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.data: list[dict] = [] if data is None else data
        self.error: Exception | None = error
        self.consultas: list[tuple[str, str | None]] = []

    def table(self, nombre: str) -> _TablaFalsa:
        """Devuelve el constructor de consultas de la tabla pedida."""
        return _TablaFalsa(self, nombre)


# -------------------------------------------------------- constantes del módulo


def test_parametros_default_tiene_exactamente_las_diez_claves_esperadas():
    """La constante es la fuente única de verdad de los 10 parámetros."""
    assert set(PARAMETROS_DEFAULT) == set(PARAMETROS_ESPERADOS)
    assert len(PARAMETROS_DEFAULT) == 10
    assert list(PARAMETROS_DEFAULT) == list(PARAMETROS_ESPERADOS)
    assert all(type(valor) is float for valor in PARAMETROS_DEFAULT.values())
    assert TABLA_PARAMETROS == "parametros_configuracion"


@pytest.mark.parametrize(("nombre", "valor"), list(PARAMETROS_ESPERADOS.items()))
def test_parametros_default_tiene_los_valores_esperados(nombre: str, valor: float):
    """Cada valor por defecto es el que está cargado en la tabla."""
    assert PARAMETROS_DEFAULT[nombre] == valor


# ------------------------------------------------- verificar_parametros (pura)


def test_verificar_parametros_pasa_con_el_dict_completo():
    """El dict completo es válido y la función no devuelve nada."""
    assert verificar_parametros(dict(PARAMETROS_DEFAULT)) is None
    # Las claves extra tampoco se rechazan: una fila nueva en la tabla no rompe
    # el contrato de los 10 parámetros.
    ampliado = {**PARAMETROS_DEFAULT, "parametro_nuevo_de_la_tabla": 1.0}
    assert verificar_parametros(ampliado) is None


@pytest.mark.parametrize(
    "faltante",
    ["abc_clase_a_pct", "eoq_min_pct", "demanda_ventana_default"],
)
def test_verificar_parametros_lanza_value_error_si_falta_una_clave(faltante: str):
    """Con una sola clave ausente, el dict es inválido."""
    incompleto = {
        nombre: valor
        for nombre, valor in PARAMETROS_DEFAULT.items()
        if nombre != faltante
    }

    with pytest.raises(ValueError):
        verificar_parametros(incompleto)


def test_verificar_parametros_lanza_value_error_si_faltan_varias_claves():
    """Con varias claves ausentes, el mensaje las reporta todas y cuenta bien."""
    faltantes = ["cv_confianza_alta", "cv_confianza_media", "score_proveedor_riesgoso"]
    incompleto = {
        nombre: valor
        for nombre, valor in PARAMETROS_DEFAULT.items()
        if nombre not in faltantes
    }

    with pytest.raises(ValueError) as error:
        verificar_parametros(incompleto)

    mensaje = str(error.value)
    assert "faltan 3 de los 10" in mensaje
    for nombre in faltantes:
        assert nombre in mensaje


def test_verificar_parametros_lanza_value_error_si_el_dict_esta_vacio():
    """Un dict vacío equivale a que falten los 10 parámetros."""
    with pytest.raises(ValueError) as error:
        verificar_parametros({})

    mensaje = str(error.value)
    assert "faltan 10 de los 10" in mensaje
    for nombre in PARAMETROS_ESPERADOS:
        assert nombre in mensaje


def test_verificar_parametros_reporta_los_nombres_faltantes_en_el_mensaje():
    """El mensaje nombra las claves ausentes y no las presentes."""
    parcial = {"abc_clase_b_pct": 95.0}

    with pytest.raises(ValueError) as error:
        verificar_parametros(parcial)

    mensaje = str(error.value)
    assert "faltan 9 de los 10" in mensaje
    for nombre in PARAMETROS_ESPERADOS:
        if nombre != "abc_clase_b_pct":
            assert nombre in mensaje
    assert "abc_clase_b_pct" not in mensaje


# ------------------------------------------------------ cargar_parametros (E/S)


def test_cargar_parametros_devuelve_los_diez_parametros_como_float():
    """Con las 10 filas en .data, devuelve el dict plano de los 10 parámetros."""
    cliente = _ClienteFalso(data=_filas(PARAMETROS_ESPERADOS))

    parametros = cargar_parametros(cliente)

    assert parametros == PARAMETROS_ESPERADOS
    assert parametros == PARAMETROS_DEFAULT
    assert all(type(valor) is float for valor in parametros.values())
    # Se lee la tabla de configuración completa, sin filtros ni escrituras.
    assert cliente.consultas == [(TABLA_PARAMETROS, "*")]


@pytest.mark.parametrize("base", ["int", "decimal", "texto"])
def test_cargar_parametros_normaliza_los_valores_a_float(base: str):
    """Valores como int, Decimal o texto se devuelven siempre como float.

    ``valor`` es ``numeric`` en la base, pero supabase-py puede devolverlo como
    ``int`` (80), ``Decimal`` (``Decimal('80')``) o como texto según el caso: el
    contrato de salida es siempre ``dict[str, float]``.
    """
    esperados = _completos(base)
    cliente = _ClienteFalso(data=_filas(esperados))

    parametros = cargar_parametros(cliente)

    assert parametros == PARAMETROS_ESPERADOS
    assert all(type(valor) is float for valor in parametros.values())
    assert type(parametros["abc_clase_a_pct"]) is float
    assert type(parametros["cv_confianza_alta"]) is float


@pytest.mark.parametrize("faltante", list(PARAMETROS_ESPERADOS))
def test_cargar_parametros_con_una_fila_de_menos_lanza_value_error(faltante: str):
    """Si a la tabla le falta una fila, el dict queda incompleto y falla."""
    filas = [
        fila
        for fila in _filas(PARAMETROS_ESPERADOS)
        if fila["nombre_parametro"] != faltante
    ]
    cliente = _ClienteFalso(data=filas)

    with pytest.raises(ValueError, match=faltante):
        cargar_parametros(cliente)

    assert cliente.consultas == [(TABLA_PARAMETROS, "*")]


def test_cargar_parametros_con_la_tabla_vacia_lanza_value_error():
    """Una tabla vacía es el caso extremo: faltan los 10 parámetros."""
    cliente = _ClienteFalso(data=[])

    with pytest.raises(ValueError) as error:
        cargar_parametros(cliente)

    mensaje = str(error.value)
    assert "faltan 10 de los 10" in mensaje
    for nombre in PARAMETROS_ESPERADOS:
        assert nombre in mensaje


@pytest.mark.parametrize(
    "error_original",
    [ConnectionError("sin conexión"), RuntimeError("401 Unauthorized")],
)
def test_cargar_parametros_propaga_la_excepcion_del_cliente(
    error_original: Exception,
):
    """Un fallo de Supabase se propaga tal cual, sin envolverlo ni capturarlo."""
    cliente = _ClienteFalso(error=error_original)

    with pytest.raises(type(error_original), match=str(error_original)) as error:
        cargar_parametros(cliente)

    assert error.value is error_original


def test_importar_config_no_carga_el_paquete_supabase():
    """Importar el módulo no tiene efectos secundarios: no carga 'supabase'.

    Se comprueba en un intérprete nuevo (no en el de pytest, donde otros tests
    pueden haber importado el paquete) para poder afirmar que importar
    ``src.config`` no se conecta a nada ni arrastra la dependencia.
    """
    codigo = "import sys, src.config; print('supabase' in sys.modules)"

    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=RAIZ_BACKEND,
        capture_output=True,
        text=True,
        check=True,
    )

    assert resultado.stdout.strip() == "False"
