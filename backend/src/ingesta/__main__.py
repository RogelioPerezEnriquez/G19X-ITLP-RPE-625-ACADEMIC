"""CLI de ingesta del dataset sintético en Supabase (RF-01).

Punto de entrada del paquete :mod:`src.ingesta`. Carga el ``.env`` de la raíz
del proyecto, crea el cliente de Supabase con la ``service_role key`` y llama a
:func:`src.ingesta.cargar_dataset.cargar_dataset` con los archivos de
``data/raw/``. Al terminar imprime el conteo de filas insertadas por tabla.

Cómo correrlo
-------------
Desde la raíz del proyecto::

    python backend/src/ingesta/__main__.py

Desde ``backend/``::

    python -m src.ingesta

Los dos caminos entran por este módulo y son equivalentes: la ruta del ``.env``
y la del dataset se derivan de ``__file__``, así que no dependen del directorio
desde el que se invoque el intérprete.

Por qué la ``service_role key``
-------------------------------
La inserción la necesita: las 7 tablas tienen RLS con políticas de solo lectura,
así que con la ``anon key`` el ``insert`` falla. El CLI usa ``SUPABASE_URL`` y
``SUPABASE_SERVICE_ROLE_KEY``, las mismas que los demos.

Qué hace
--------
1. Carga ``.env`` desde la raíz del proyecto (robusto ante el cwd, porque la
   ruta se deriva de ``__file__``).
2. Crea el cliente con la ``service_role key``.
3. Llama a :func:`cargar_dataset` con ``data/raw/``.
4. Imprime el conteo de filas insertadas por tabla.

Códigos de salida
-----------------
* ``0``: las 4 tablas se cargaron.
* ``1``: falta el ``.env`` o alguna de sus variables, no se pudo crear el
  cliente, o :func:`cargar_dataset` falló. En todos los casos se imprime la
  causa antes de salir.

Contrato de errores de :func:`cargar_dataset`
---------------------------------------------
El CLI no reinterpreta el error: imprime ``type(exc).__name__`` y el mensaje y
sale con código 1. Cada tipo tiene un encabezado propio para que el origen se
lea de un vistazo:

* ``FileNotFoundError``: falta alguno de los 4 archivos en ``data/raw/``.
* ``ValueError``: columnas faltantes, nulos, claves repetidas o referencias
  rotas entre archivos.
* ``RuntimeError``: alguna de las 4 tablas ya tiene datos (sugiere el
  ``truncate``) o falta ``openpyxl`` para leer un ``.xlsx``.
* Cualquier otro error de Supabase (lectura o escritura, p. ej. un error de
  PostgREST) se reporta como "falló la ingesta".
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

# --- Rutas derivadas de __file__ ---------------------------------------------
# 'backend/src/ingesta/__main__.py': parents[3] es la raíz del proyecto.
RAIZ_PROYECTO: Path = Path(__file__).resolve().parents[3]
BACKEND: Path = RAIZ_PROYECTO / "backend"

# Se agrega 'backend' (el padre de 'src'), no 'backend/src', para que el import
# absoluto de abajo funcione también cuando se corre el archivo directamente.
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Este import va después de ajustar el sys.path (de ahí el noqa: E402).
from src.ingesta.cargar_dataset import cargar_dataset  # noqa: E402

# El dataset de ejemplo vive en 'data/raw' en la raíz del proyecto, no junto a
# este archivo: se resuelve contra RAIZ_PROYECTO y no contra el cwd, para que
# 'python -m src.ingesta' (desde 'backend/') lea el mismo directorio.
DIRECTORIO_DATOS: Path = RAIZ_PROYECTO / "data" / "raw"

# Ancho de las líneas separadoras del reporte (misma convención que los demos).
ANCHO_REPORTE: int = 78

TITULO_REPORTE: str = "INGESTA DEL DATASET EN SUPABASE"


def _crear_cliente() -> "Client":
    """Crea el cliente de Supabase con la ``service_role key``.

    Returns:
        Cliente de Supabase listo para escribir.

    Raises:
        SystemExit: si faltan ``SUPABASE_URL`` o ``SUPABASE_SERVICE_ROLE_KEY`` en
            el entorno, o si el cliente no se puede crear (por ejemplo, por una
            URL inválida).
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
        print(f"       Causa: {type(error).__name__}: {error}")
        raise SystemExit(1) from error


def _imprimir_cabecera(titulo: str) -> None:
    """Imprime un título enmarcado con ``=`` (texto plano, sin ANSI)."""
    print()
    print("=" * ANCHO_REPORTE)
    print(titulo)
    print("=" * ANCHO_REPORTE)


def _imprimir_reporte(conteos: dict[str, int]) -> None:
    """Imprime el conteo de filas insertadas por tabla.

    Args:
        conteos: dict devuelto por :func:`cargar_dataset`, ``{tabla: filas}``, en
            el orden de carga. El dict conserva ese orden, así que se recorre
            directamente sin reordenar.
    """
    print()
    print("-" * ANCHO_REPORTE)
    print("FILAS INSERTADAS POR TABLA")
    print("-" * ANCHO_REPORTE)
    print(f"{'Tabla':<24}{'Filas insertadas':>18}")
    print("-" * ANCHO_REPORTE)
    for tabla, filas in conteos.items():
        print(f"{tabla:<24}{filas:>18}")
    print("-" * ANCHO_REPORTE)
    print(f"{'TOTAL':<24}{sum(conteos.values()):>18}")


def main() -> int:
    """Carga el dataset de ``data/raw/`` en Supabase.

    Returns:
        Código de salida del proceso: 0 si las 4 tablas se cargaron y 1 si faltó
        el ``.env``, faltaron credenciales o falló la ingesta.
    """
    ruta_env: Path = RAIZ_PROYECTO / ".env"
    if not ruta_env.is_file():
        print(f"ERROR: no se encontro el archivo .env en {ruta_env}.")
        print("       Copie .env.example a .env y complete SUPABASE_URL y")
        print("       SUPABASE_SERVICE_ROLE_KEY (Supabase -> Settings -> API).")
        return 1

    load_dotenv(ruta_env)

    supabase: Client = _crear_cliente()

    _imprimir_cabecera(TITULO_REPORTE)
    print()
    print(f"Directorio del dataset: {DIRECTORIO_DATOS}")

    try:
        conteos: dict[str, int] = cargar_dataset(DIRECTORIO_DATOS, supabase)
    except FileNotFoundError as error:
        print()
        print("ERROR: falta uno de los archivos del dataset en 'data/raw'.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1
    except ValueError as error:
        print()
        print("ERROR: el dataset no paso la validacion.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1
    except RuntimeError as error:
        print()
        print("ERROR: no se puede cargar el dataset en el estado actual.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print()
        print("ERROR: fallo la ingesta contra Supabase (lectura o insercion).")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1

    print()
    print("Carga completada sin errores.")
    _imprimir_reporte(conteos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

