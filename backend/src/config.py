"""Parámetros de configuración del sistema (fase 4: configurabilidad).

Este módulo es el **único punto de entrada** de los umbrales y parámetros
ajustables: cada módulo del motor recibirá sus umbrales como argumento, y quien
los lee de la base de datos lo hace desde aquí.

Qué contiene
------------
* :data:`PARAMETROS_DEFAULT`: **fuente única de verdad** de los valores por
  defecto del sistema. Es un dict constante a nivel de módulo (no se recalcula)
  con los 10 parámetros de la tabla ``parametros_configuracion`` de
  ``db/schema.sql`` y sus valores actuales. Los módulos del motor importan de
  aquí sus *defaults*.
* :func:`cargar_parametros`: E/S. Única función del módulo que toca Supabase.
* :func:`verificar_parametros`: pura. No accede a red ni a base de datos.

Sin efectos secundarios al importar
-----------------------------------
Importar este módulo **no** se conecta a Supabase: solo define la constante y
las funciones. El paquete ``supabase`` se importa únicamente para el chequeo de
tipos (``TYPE_CHECKING``), así que el módulo no depende de él en tiempo de
ejecución.

Contrato de errores
-------------------
* :func:`verificar_parametros`: ``ValueError`` si falta alguna clave de
  :data:`PARAMETROS_DEFAULT`, indicando qué parámetros faltan.
* :func:`cargar_parametros`: ``ValueError`` si a la tabla le falta algún
  parámetro; los errores de la API de Supabase se propagan tal cual. Una tabla
  vacía es un caso particular del anterior (faltarían todos) y no se captura en
  silencio.

Casos borde
-----------
* La columna ``valor`` es ``numeric`` en la base, pero supabase-py puede
  devolver ``int``, ``float``, ``Decimal`` o incluso el número como texto según
  el caso, así que todos los valores se convierten con ``float(...)``.
* :func:`cargar_parametros` no filtra claves: si la tabla trae parámetros
  nuevos que no están en :data:`PARAMETROS_DEFAULT`, se devuelven también (la
  verificación solo exige que estén las esperadas). Así, añadir una fila nueva
  en la base no rompe el contrato de las 10 claves que esperan los llamadores.
* Los parámetros se devuelven **todos** como ``float``, incluso los que son
  conceptualmente enteros (p. ej. ``demanda_ventana_default = 6.0``): el cast a
  ``int`` es responsabilidad del módulo que los consume.
* Este módulo **no** valida rangos numéricos: cada módulo del motor valida sus
  propios umbrales (mismo criterio que el resto del motor).

Unidades
--------
Los ``*_pct`` de :data:`PARAMETROS_DEFAULT` están en **porcentaje** (80.0, 3.0),
igual que sus constantes homólogas en el motor. Ojo con ``eoq_min_pct`` y
``eoq_max_pct``: ``src.evaluador`` los usa como fracción (``RATIO_MIN``,
``RATIO_MAX``), así que el módulo que los reciba debe dividirlos entre 100,
como ya hace ``src.motor.ahorro`` con ``umbral_ahorro_pct``.

"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - solo para las anotaciones de tipo
    # El cliente se importa solo para el chequeo de tipos: así el módulo no
    # depende del paquete 'supabase' en tiempo de ejecución y los tests de la
    # función pura no lo necesitan.
    from supabase import Client

__all__ = [
    "PARAMETROS_DEFAULT",
    "TABLA_PARAMETROS",
    "cargar_parametros",
    "verificar_parametros",
]

# Tabla de la que lee :func:`cargar_parametros`.
TABLA_PARAMETROS: str = "parametros_configuracion"

# Fuente única de verdad de los valores por defecto del sistema: los 10
# parámetros de 'parametros_configuracion' (db/schema.sql) con sus valores
# actuales, que coinciden con las constantes de los módulos del motor:
#   Los umbrales de ABC (abc_clase_a_pct, abc_clase_b_pct) son consumidos por
#   src.motor.abc.clasificar_abc a través de umbral_clase_a y umbral_clase_b
#   ahorro_neto_min_pct       -> src.motor.ahorro.UMBRAL_AHORRO_PCT_DEFAULT
#   cv_confianza_alta         -> src.motor.xyz.UMBRAL_X
#   cv_confianza_media        -> src.motor.xyz.UMBRAL_Y
#   demanda_ventana_default   -> src.motor.demanda.VENTANA_DEFAULT
#   eoq_max_pct               -> src.evaluador.RATIO_MAX (allí, fracción)
#   eoq_min_pct               -> src.evaluador.RATIO_MIN (allí, fracción)
#   score_proveedor_confiable -> src.motor.proveedor.UMBRAL_CONFIABLE
#   score_proveedor_riesgoso  -> src.motor.proveedor.UMBRAL_RIESGOSO
PARAMETROS_DEFAULT: dict[str, float] = {
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


def verificar_parametros(parametros: dict[str, float]) -> None:
    """
    Valida que el dict contiene todas las claves esperadas.

    Función pura: no accede a red ni a base de datos y no modifica el dict que
    recibe. Solo comprueba la **presencia** de las claves de
    :data:`PARAMETROS_DEFAULT`; los rangos numéricos los valida cada módulo del
    motor con sus propios criterios. Las claves extra no se rechazan.

    Args:
        parametros: dict a verificar.

    Raises:
        ValueError: si falta alguna clave de :data:`PARAMETROS_DEFAULT`. El
            mensaje lista los parámetros faltantes.
    """
    faltantes: list[str] = [
        nombre for nombre in PARAMETROS_DEFAULT if nombre not in parametros
    ]
    if faltantes:
        raise ValueError(
            f"verificar_parametros: faltan {len(faltantes)} de los "
            f"{len(PARAMETROS_DEFAULT)} parámetros de configuración de "
            f"'{TABLA_PARAMETROS}': {', '.join(faltantes)}."
        )


def cargar_parametros(supabase_client: "Client") -> dict[str, float]:
    """
    Carga los parámetros de configuración desde Supabase.

    Lee la tabla :data:`TABLA_PARAMETROS` (estructura vertical:
    ``nombre_parametro | valor | descripcion``) y la aplana a
    ``{nombre_parametro: float(valor)}``. Es la única función del módulo que
    hace E/S.

    Args:
        supabase_client: cliente de Supabase (con permisos de lectura). Alcanza
            con la ``anon key`` porque la tabla tiene políticas de solo lectura
            (``db/schema.sql``).

    Returns:
        dict {nombre_parametro: valor} con los 10 parámetros.

    Raises:
        ValueError: si falta algún parámetro esperado, incluido el caso de una
            tabla vacía (faltarían todos).
        Exception: si Supabase falla (propaga la excepción original).

    Notas:
        - La conversión a ``float`` es explícita porque la columna es ``numeric``
          y el cliente puede devolver ``int``, ``float``, ``Decimal`` o texto.
        - No filtra claves: los parámetros de la tabla que no estén en
          :data:`PARAMETROS_DEFAULT` también se devuelven.
        - No modifica nada en la base ni en el cliente.
    """
    respuesta = supabase_client.table(TABLA_PARAMETROS).select("*").execute()
    parametros: dict[str, float] = {
        fila["nombre_parametro"]: float(fila["valor"]) for fila in respuesta.data
    }
    verificar_parametros(parametros)
    return parametros
