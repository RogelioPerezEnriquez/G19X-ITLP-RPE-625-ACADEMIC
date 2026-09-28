"""Demo end-to-end del recomendador contra los datos reales del seed en Supabase.

Proposito
---------
Verificar que el motor OR y :mod:`src.recomendador` funcionan contra la base de
datos real (y no solo contra los DataFrames que construyen los tests): lee las
cuatro tablas de Supabase con la ``service_role key``, genera las recomendaciones
de compra, las muestra en un reporte legible por consola y, opcionalmente, las
guarda en la tabla ``recomendaciones`` si el usuario lo confirma.

Como correrlo
-------------
Desde la raiz del proyecto::

    python scripts/demo_recomendador.py

El script carga las variables de ``.env`` (en la raiz) y usa ``SUPABASE_URL`` y
``SUPABASE_SERVICE_ROLE_KEY``. La ``service_role key`` es necesaria porque el
script lee todas las tablas y, si se confirma, escribe en ``recomendaciones``
(esa tabla tiene RLS habilitado con politicas de solo lectura, asi que la
``anon key`` no alcanza para guardar).

Que hace
--------
1. Carga ``.env`` desde la raiz del proyecto (robusto ante el cwd, porque la
   ruta se deriva de ``__file__``).
2. Crea el cliente de Supabase con la ``service_role key`` y comprueba la
   conectividad con una lectura minima.
3. Llama a ``generar_recomendaciones(supabase)`` (lectura de las 4 tablas +
   motor OR).
4. Imprime un reporte con una fila por producto (proveedor elegido, clase
   ABC/XYZ, urgencia, stock actual vs punto de reorden, cantidad recomendada y
   ahorro neto) y un resumen agregado al final.
5. Pregunta si guardar y, solo con respuesta afirmativa, llama a
   ``guardar_recomendaciones(supabase, recomendaciones)``, captura el DataFrame
   que devuelve (las filas ya persistidas, con el ``id`` uuid que genero Supabase)
   y lo muestra en pantalla. Esos ``id`` son el ``recomendacion_id`` que necesita
   el evaluador de la rubrica (``backend/src/evaluador.py``): el script deja el
   flujo listo para llamarlo despues.

Que NO hace
-----------
- No modifica el motor, el recomendador ni ningun otro archivo del repositorio.
- No inserta datos de prueba en ``productos``/``proveedores`` (para eso estan
  ``db/seed_sintetico.sql`` y ``scripts/verificar_*.py``).
- No borra ni limpia recomendaciones existentes: ``guardar_recomendaciones``
  solo inserta filas nuevas.
- No calcula la rubrica de 6 criterios ni escribe en ``evaluaciones_criterios``:
  solo deja a la vista los ``id`` que devuelve el guardado, que son la entrada de
  ese evaluador.
- No usa colores ANSI ni emojis: la salida es texto plano pensado para Windows.

Decision de import (``sys.path``)
---------------------------------
``backend/src/recomendador.py`` importa los seis modulos del motor con rutas
absolutas (``from src.motor.abc import ...``), de modo que su paquete padre
``src`` tiene que ser importable. Agregar ``backend/src`` al ``sys.path`` no
alcanza: ``src`` quedaria fuera del path y el import interno del motor fallaria
con ``ModuleNotFoundError``. Por eso se agrega ``backend`` (el padre de ``src``)
y se importa como ``src.recomendador``, que es exactamente como lo hacen los
tests (``backend/tests/test_recomendador.py``).

Contrato de errores
-------------------
- ``.env`` ausente: mensaje claro y salida con codigo 1.
- Cliente de Supabase no creado o sin conexion: mensaje claro y salida con
  codigo 1.
- Fallo del recomendador o del guardado: la excepcion se propaga tal cual (no se
  captura en silencio) para no ocultar la causa real.
"""

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

# --- Rutas e import del backend ---------------------------------------------
# Ver "Decision de import" en el docstring: se agrega 'backend' (el padre de
# 'src'), no 'backend/src', para que funcionen los imports absolutos del motor.
RAIZ_PROYECTO: Path = Path(__file__).resolve().parent.parent
BACKEND: Path = RAIZ_PROYECTO / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Estos imports van despues de ajustar el sys.path (de ahi el noqa: E402).
from src.motor.ahorro import ESTADO_AHORRO  # noqa: E402
from src.recomendador import (  # noqa: E402
    ORDEN_URGENCIA,
    generar_recomendaciones,
    guardar_recomendaciones,
)

# Ancho de las lineas separadoras del reporte.
ANCHO_REPORTE: int = 78

# Respuestas afirmativas aceptadas al preguntar si se guarda.
RESPUESTAS_AFIRMATIVAS: frozenset[str] = frozenset({"s", "si", "y", "yes"})


def _crear_cliente() -> Client:
    """Crea el cliente de Supabase con la ``service_role key``.

    Returns:
        Cliente de Supabase listo para usar.

    Raises:
        SystemExit: si faltan ``SUPABASE_URL`` o ``SUPABASE_SERVICE_ROLE_KEY``, o
            si el cliente no se puede crear (por ejemplo, por una URL invalida).
    """
    url: str | None = os.environ.get("SUPABASE_URL")
    service_key: str | None = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not service_key:
        print("ERROR: faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en el .env.")
        print("       La service_role key esta en Supabase -> Settings -> API.")
        raise SystemExit(1)

    try:
        return create_client(url, service_key)
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print("ERROR: no se pudo crear el cliente de Supabase.")
        print(f"       Causa: {error}")
        raise SystemExit(1) from error


def _verificar_conexion(supabase: Client) -> None:
    """Comprueba la conectividad con una lectura minima de la tabla ``productos``.

    Args:
        supabase: cliente de Supabase ya configurado.

    Raises:
        SystemExit: si la lectura falla (red, credenciales, tabla inexistente).
    """
    try:
        supabase.table("productos").select("id").limit(1).execute()
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print("ERROR: no se pudo conectar a Supabase o leer la tabla 'productos'.")
        print(f"       Causa: {error}")
        raise SystemExit(1) from error


def _formato_numero(valor: float) -> str:
    """Formatea un numero con separador de miles y dos decimales."""
    return f"{valor:,.2f}"


def _imprimir_tabla(encabezados: list[str], filas: list[list[str]]) -> None:
    """Imprime una tabla de texto plano con ``|`` y ``-`` (sin ANSI ni emojis).

    Args:
        encabezados: titulos de las columnas.
        filas: filas ya convertidas a texto, con la misma cantidad de celdas que
            ``encabezados``.
    """
    anchos: list[int] = [len(encabezado) for encabezado in encabezados]
    for fila in filas:
        for indice, celda in enumerate(fila):
            anchos[indice] = max(anchos[indice], len(celda))

    def _linea(valores: list[str]) -> str:
        celdas = " | ".join(
            valor.ljust(anchos[indice]) for indice, valor in enumerate(valores)
        )
        return f"| {celdas} |"

    separador = "|" + "|".join("-" * (ancho + 2) for ancho in anchos) + "|"
    print(_linea(encabezados))
    print(separador)
    for fila in filas:
        print(_linea(fila))


def _imprimir_reporte(recomendaciones: pd.DataFrame) -> None:
    """Imprime el encabezado y una fila por recomendacion.

    Args:
        recomendaciones: DataFrame devuelto por
            :func:`src.recomendador.generar_recomendaciones`.
    """
    print()
    print("=" * ANCHO_REPORTE)
    print("REPORTE DE RECOMENDACIONES DE COMPRA")
    print("=" * ANCHO_REPORTE)
    print(f"Recomendaciones generadas: {len(recomendaciones)}")
    print()

    if recomendaciones.empty:
        print("No hay recomendaciones: ningun producto cumple los criterios minimos")
        print("(al menos 2 periodos de historial, proveedor asociado y CV calculable).")
        return

    encabezados: list[str] = [
        "producto_id",
        "nombre",
        "proveedor",
        "ABC",
        "XYZ",
        "urgencia",
        "stock_actual",
        "punto_reorden",
        "cantidad_rec",
        "ahorro_neto",
    ]
    filas: list[list[str]] = [
        [
            str(fila["producto_id"]),
            str(fila["nombre"]),
            str(fila["proveedor_nombre"]),
            str(fila["clase_abc"]),
            str(fila["clase_xyz"]),
            str(fila["urgencia"]),
            _formato_numero(float(fila["stock_actual"])),
            _formato_numero(float(fila["punto_reorden"])),
            _formato_numero(float(fila["cantidad_recomendada"])),
            _formato_numero(float(fila["ahorro_neto_estimado"])),
        ]
        for _, fila in recomendaciones.iterrows()
    ]
    _imprimir_tabla(encabezados, filas)
    print()
    print("Leyenda: ABC/XYZ = clasificacion del producto; urgencia comparada contra")
    print("stock_seguridad (Critico) y punto_reorden (Atencion).")


def _imprimir_resumen(recomendaciones: pd.DataFrame) -> None:
    """Imprime el resumen agregado (urgencia, ahorro y ahorro total).

    Args:
        recomendaciones: DataFrame devuelto por
            :func:`src.recomendador.generar_recomendaciones`.
    """
    print()
    print("-" * ANCHO_REPORTE)
    print("RESUMEN")
    print("-" * ANCHO_REPORTE)

    if recomendaciones.empty:
        print("Sin filas que resumir.")
        return

    conteo_urgencia = recomendaciones["urgencia"].value_counts()
    print("Recomendaciones por urgencia:")
    for urgencia in ORDEN_URGENCIA:
        print(f"  - {urgencia:<11}: {int(conteo_urgencia.get(urgencia, 0))}")

    con_ahorro = int((recomendaciones["estado_ahorro"] == ESTADO_AHORRO).sum())
    ahorro_total = float(recomendaciones["ahorro_neto_estimado"].sum())

    print()
    print(f"Recomendaciones con '{ESTADO_AHORRO}': {con_ahorro}")
    print(f"Suma de ahorro_neto_estimado: {_formato_numero(ahorro_total)}")


def _imprimir_guardadas(guardadas: pd.DataFrame) -> None:
    """Imprime los ids que Supabase asigno a las recomendaciones guardadas.

    Args:
        guardadas: DataFrame devuelto por
            :func:`src.recomendador.guardar_recomendaciones`: las filas insertadas
            en la tabla 'recomendaciones', con su 'id' (uuid), su
            'fecha_generacion' y el resto de las columnas de la tabla.
    """
    print()
    print("-" * ANCHO_REPORTE)
    print("RECOMENDACIONES GUARDADAS")
    print("-" * ANCHO_REPORTE)

    if guardadas.empty or "id" not in guardadas.columns:
        print("Supabase no devolvio las filas insertadas: no hay ids que mostrar.")
        print("Las recomendaciones igual quedaron guardadas en la tabla.")
        return

    encabezados: list[str] = ["producto_id", "id"]
    filas: list[list[str]] = [
        [str(fila["producto_id"]), str(fila["id"])] for _, fila in guardadas.iterrows()
    ]
    _imprimir_tabla(encabezados, filas)
    print()
    print(f"Filas devueltas por el insert: {len(guardadas)}")
    print("El 'id' (uuid) de cada fila es el 'recomendacion_id' que necesita la")
    print("rubrica de 6 criterios (backend/src/evaluador.py). Como el insert solo")
    print("devuelve las columnas de la tabla, hay que cruzar estos ids con el")
    print("reporte (por producto_id) para armar la entrada del evaluador.")


def _preguntar_guardar() -> bool:
    """Pregunta si se quieren guardar las recomendaciones en Supabase.

    Returns:
        ``True`` si el usuario responde que si; ``False`` en cualquier otra
        respuesta o si no hay entrada estandar disponible (por ejemplo, cuando el
        script se corre sin consola interactiva).
    """
    try:
        respuesta = input(
            "Desea guardar estas recomendaciones en Supabase? [S/N]: "
        )
    except EOFError:
        print("Sin entrada estandar disponible: no se guardo nada.")
        return False
    return respuesta.strip().lower() in RESPUESTAS_AFIRMATIVAS


def main() -> int:
    """Punto de entrada del demo.

    Returns:
        Codigo de salida del proceso: 0 si todo fue bien (incluido el caso de no
        guardar), 1 si falta el ``.env``, faltan credenciales o no hay conexion.
    """
    ruta_env: Path = RAIZ_PROYECTO / ".env"
    if not ruta_env.is_file():
        print(f"ERROR: no se encontro el archivo .env en {ruta_env}.")
        print("       Copie .env.example a .env y complete SUPABASE_URL y")
        print("       SUPABASE_SERVICE_ROLE_KEY (Supabase -> Settings -> API).")
        return 1

    load_dotenv(ruta_env)

    supabase: Client = _crear_cliente()
    _verificar_conexion(supabase)

    # Un fallo del recomendador o del guardado se propaga tal cual: no se captura
    # en silencio, para que la causa real quede visible en el traceback.
    recomendaciones: pd.DataFrame = generar_recomendaciones(supabase)

    _imprimir_reporte(recomendaciones)
    _imprimir_resumen(recomendaciones)

    if recomendaciones.empty:
        print()
        print("No hay recomendaciones que guardar. Fin.")
        return 0

    print()
    if not _preguntar_guardar():
        print("Operacion cancelada: no se escribio nada en Supabase.")
        return 0

    guardadas: pd.DataFrame = guardar_recomendaciones(supabase, recomendaciones)
    print()
    print(
        f"OK: se guardaron {len(recomendaciones)} recomendaciones en la tabla "
        "'recomendaciones'."
    )
    _imprimir_guardadas(guardadas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
