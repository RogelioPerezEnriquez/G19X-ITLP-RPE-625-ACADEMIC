"""Carga un dataset (CSV/Excel) en Supabase (RF-01).

Script de ingesta del MVP, separado del motor de cálculo: no importa nada de
``src.motor``, ``src.recomendador`` ni ``src.evaluador``. Lee los cuatro
archivos de datos del dataset (productos, proveedores, producto_proveedor e
historial_demanda), los valida y los inserta en las tablas de Supabase,
resolviendo por nombre las claves foráneas: los archivos de origen usan nombres
legibles y los UUID de productos y proveedores los genera Supabase
(``gen_random_uuid()``, ver ``db/schema.sql``).

Cómo correrlo
-------------
Desde ``backend/``::

    python -m src.ingesta

Desde la raíz del proyecto::

    python backend/src/ingesta/__main__.py

Los dos caminos entran por :mod:`src.ingesta.__main__` y son equivalentes. El
CLI carga el ``.env`` de la raíz, crea el cliente con
``SUPABASE_SERVICE_ROLE_KEY`` (la escritura necesita ``service_role``: las 7
tablas tienen RLS con políticas de solo lectura) y llama a
:func:`cargar_dataset` con ``data/raw/``.

Qué hace
--------
1. Verifica que las 4 tablas de datos estén vacías. Si alguna tiene filas,
   falla: este script **nunca** borra ni sobrescribe datos.
2. Lee los 4 archivos de ``data/raw/``, en ``.csv`` (primero) o ``.xlsx``.
3. Valida columnas requeridas, celdas nulas en columnas obligatorias, claves
   repetidas dentro de un archivo e integridad referencial entre archivos.
   Toda la validación ocurre **antes** de la primera escritura.
4. Inserta en orden de dependencias y resuelve las claves foráneas con una
   consulta por tabla referenciada más un mapeo vectorizado de pandas.
5. Devuelve el conteo de filas insertadas por tabla (lo imprime el CLI).

Orden de carga
--------------
::

    productos -> proveedores -> producto_proveedor -> historial_demanda

Las dos primeras no tienen claves foráneas y las otras dos dependen de sus
UUID, así que van después. Los mapas {nombre: uuid} se leen de la base
**después** de insertar productos y proveedores: los UUID no existen antes de
esa inserción.

Cómo vaciar las tablas
----------------------
Para volver a cargar el dataset hay que vaciar las tablas de datos y también
las de salida del motor, porque ``recomendaciones.proveedor_id`` es
``on delete restrict`` y bloquea el borrado de un proveedor referenciado::

    truncate table evaluaciones_criterios, recomendaciones, historial_demanda,
        producto_proveedor, productos, proveedores restart identity cascade;

Es la misma sentencia que documenta ``db/seed_sintetico.sql``. El script no la
ejecuta por su cuenta: solo la sugiere en el mensaje de error.

Contrato de errores
-------------------
* ``FileNotFoundError``: falta alguno de los 4 archivos en ``data_dir``.
* ``ValueError``: columnas faltantes, nulos en columnas obligatorias, claves
  repetidas, referencias rotas entre archivos o nombres que no se pueden
  resolver a un único UUID. Reporta **todas** las filas afectadas.
* ``RuntimeError``: alguna de las 4 tablas ya tiene datos, o falta ``openpyxl``
  para leer un ``.xlsx``.
* Cualquier otra excepción de Supabase se propaga tal cual (modo todo-o-nada),
  con una nota que indica en qué tabla falló la inserción.

Casos borde
-----------
* ``productos.nombre`` y ``proveedores.nombre`` son ``text not null`` **sin**
  restricción ``unique`` en el schema. Un nombre repetido en la tabla no se
  puede resolver a un único UUID: se reporta como error en lugar de elegir uno
  al azar.
* Si un archivo existe como ``.csv`` y como ``.xlsx``, gana el ``.csv``.
* ``.xlsx`` necesita ``openpyxl``, que no está en ``backend/requirements.txt``
  (el MVP solo usa CSV): si falta, el error explica cómo instalarlo o cómo
  exportar el archivo a CSV.
* Los rangos y dominios de las columnas (``>= 0``, ``between 0 and 100``) no se
  revalidan aquí: los aplica la base con sus restricciones ``check``.
* La inserción no se trocea: el dataset del MVP (90 filas) entra en una sola
  petición. Un dataset que superara el tamaño máximo del cuerpo de PostgREST
  necesitaría insertar por lotes.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - solo para las anotaciones de tipo
    # El cliente se importa solo para el chequeo de tipos (misma convención que
    # src/config.py): así el módulo no depende del paquete 'supabase' en tiempo
    # de ejecución y sus validaciones se pueden probar sin conexión.
    from supabase import Client

__all__ = ["cargar_dataset"]

# Tablas de datos que carga este script, en orden de dependencias. Son las que
# se verifican vacías antes de insertar y las claves del dict que devuelve
# :func:`cargar_dataset`.
TABLAS_DATOS: tuple[str, ...] = (
    "productos",
    "proveedores",
    "producto_proveedor",
    "historial_demanda",
)

# Extensiones aceptadas, en orden de precedencia: si el archivo existe en los
# dos formatos, se lee el CSV.
EXTENSIONES: tuple[str, ...] = (".csv", ".xlsx")

# Columnas que debe traer cada archivo (los nombres que ve el usuario, no los
# de la tabla: producto_proveedor e historial_demanda referencian productos y
# proveedores por nombre).
COLUMNAS_PRODUCTOS: tuple[str, ...] = (
    "nombre",
    "categoria",
    "costo_unitario",
    "stock_actual",
    "costo_ordenar",
    "costo_mantener_pct_anual",
)

COLUMNAS_PROVEEDORES: tuple[str, ...] = (
    "nombre",
    "cumplimiento_entrega_pct",
    "tasa_defectos_pct",
)

COLUMNAS_PRODUCTO_PROVEEDOR: tuple[str, ...] = (
    "producto_nombre",
    "proveedor_nombre",
    "precio_unitario",
    "lead_time_dias",
    "cantidad_umbral_descuento",
    "descuento_pct",
)

COLUMNAS_HISTORIAL: tuple[str, ...] = (
    "producto_nombre",
    "periodo",
    "cantidad_demandada",
)

# Columnas NOT NULL de cada tabla (sin contar 'id' ni 'creado_en', que los pone
# Supabase). Son las que se validan sin nulos; las demás columnas del archivo
# admiten nulos en la base y un nulo significa "sin dato" (por ejemplo, un
# producto sin descuento por volumen).
NO_NULAS_PRODUCTOS: tuple[str, ...] = (
    "nombre",
    "costo_unitario",
    "stock_actual",
    "costo_ordenar",
    "costo_mantener_pct_anual",
)

NO_NULAS_PROVEEDORES: tuple[str, ...] = (
    "nombre",
    "cumplimiento_entrega_pct",
    "tasa_defectos_pct",
)

NO_NULAS_PRODUCTO_PROVEEDOR: tuple[str, ...] = (
    "producto_nombre",
    "proveedor_nombre",
    "precio_unitario",
    "lead_time_dias",
)

NO_NULAS_HISTORIAL: tuple[str, ...] = (
    "producto_nombre",
    "periodo",
    "cantidad_demandada",
)

# Claves que no se pueden repetir dentro de un archivo. En productos y
# proveedores no hay UNIQUE de nombre en el schema, pero un nombre repetido
# haría ambigua la resolución de la clave foránea; en producto_proveedor y
# historial_demanda coinciden con la PK y el UNIQUE (producto_id, periodo) de
# la tabla, así que un duplicado lo rechazaría la base.
CLAVES_PRODUCTOS: tuple[str, ...] = ("nombre",)
CLAVES_PROVEEDORES: tuple[str, ...] = ("nombre",)
CLAVES_PRODUCTO_PROVEEDOR: tuple[str, ...] = ("producto_nombre", "proveedor_nombre")
CLAVES_HISTORIAL: tuple[str, ...] = ("producto_nombre", "periodo")

# Nombres de las columnas que se usan como clave de unión entre archivos.
COLUMNA_PRODUCTO_NOMBRE: str = "producto_nombre"
COLUMNA_PROVEEDOR_NOMBRE: str = "proveedor_nombre"
# Nombre de la columna 'nombre' de las tablas referenciadas (productos y
# proveedores): es la que se resuelve contra los *_nombre de los archivos.
COLUMNA_NOMBRE: str = "nombre"
# Nombres de las claves foráneas que se agregan al DataFrame. Son los que
# espera la tabla (mismos que usa src.recomendador al leer).
COLUMNA_PRODUCTO_ID: str = "producto_id"
COLUMNA_PROVEEDOR_ID: str = "proveedor_id"

# Columna de fecha y columnas que son 'integer' en la base. El periodo se
# normaliza a ISO antes de insertar y las enteras se convierten a int de Python
# (una columna con un nulo se lee como float y Postgres rechazaría
# 'lead_time_dias': 7.0, que es JSON válido pero no siempre un entero válido).
COLUMNA_PERIODO: str = "periodo"
COLUMNAS_ENTERAS: dict[str, tuple[str, ...]] = {
    "producto_proveedor": ("lead_time_dias",),
}

# Columnas que debe tener exactamente el DataFrame que se inserta en cada
# tabla. Es la red de seguridad de :func:`_insertar_tabla`: si sobra una columna
# (por ejemplo, una columna de nombre que no se descartó) o falta una, PostgREST
# devolvería un error genérico a mitad de la carga y el dataset quedaría a
# medias. 'id' y 'creado_en' no están: los pone Supabase.
COLUMNAS_TABLA: dict[str, tuple[str, ...]] = {
    "productos": (
        "nombre",
        "categoria",
        "costo_unitario",
        "stock_actual",
        "costo_ordenar",
        "costo_mantener_pct_anual",
    ),
    "proveedores": (
        "nombre",
        "cumplimiento_entrega_pct",
        "tasa_defectos_pct",
    ),
    "producto_proveedor": (
        "producto_id",
        "proveedor_id",
        "precio_unitario",
        "lead_time_dias",
        "cantidad_umbral_descuento",
        "descuento_pct",
    ),
    "historial_demanda": (
        "producto_id",
        "periodo",
        "cantidad_demandada",
    ),
}

# Sentencia sugerida cuando alguna tabla ya tiene datos. Es la de
# db/seed_sintetico.sql; se repite aquí porque el error tiene que ser
# accionable sin abrir otro archivo.
TRUNCATE_SUGERIDO: str = (
    "truncate table evaluaciones_criterios, recomendaciones, historial_demanda, "
    "producto_proveedor, productos, proveedores restart identity cascade;"
)


def cargar_dataset(data_dir: Path, supabase_client: "Client") -> dict[str, int]:
    """
    Carga el dataset completo desde data_dir a Supabase.

    Orquesta las cinco etapas de la ingesta: verificar que las tablas estén
    vacías, leer y validar los 4 archivos, insertar las tablas sin claves
    foráneas, resolver las claves foráneas contra los UUID ya insertados e
    insertar las dos tablas dependientes. Es la única función pública del
    módulo; el resto son ayudantes privados y sin estado.

    Args:
        data_dir: directorio con los archivos (``productos.csv``,
            ``proveedores.csv``, ``producto_proveedor.csv`` y
            ``historial_demanda.csv``, con sus equivalentes ``.xlsx``).
        supabase_client: cliente de Supabase con la **service_role key**. La
            escritura la necesita: las 7 tablas tienen RLS con políticas de
            solo lectura, así que con la ``anon key`` el ``insert`` falla. La
            lectura de los mapas de claves foráneas pasa por el mismo cliente.

    Returns:
        dict {tabla: filas insertadas} con las 4 claves de
        :data:`TABLAS_DATOS`, en orden de carga.

    Raises:
        FileNotFoundError: si falta alguno de los 4 archivos en ``data_dir``.
        ValueError: si algún archivo tiene columnas faltantes, nulos en
            columnas obligatorias, claves repetidas, referencias a productos o
            proveedores que no están en su propio archivo, o valores de
            ``periodo`` que no se pueden interpretar como fecha.
        RuntimeError: si alguna de las 4 tablas ya tiene datos (el mensaje dice
            cuáles y sugiere el ``truncate``), o si falta ``openpyxl`` para
            leer un ``.xlsx``.
        Exception: cualquier error de la API de Supabase se propaga tal cual
            (modo todo-o-nada) con una nota que indica en qué tabla falló.

    Notas:
        - Es una función de E/S: lee archivos, lee y escribe en Supabase. No
          imprime nada (el reporte es del CLI), no borra filas y no modifica
          ``parametros_configuracion``.
        - El orden de las etapas importa. Los 4 archivos se leen y se validan
          **antes** de la primera escritura, así que un archivo mal formado no
          deja la base a medias. Los mapas {nombre: uuid} se leen **después**
          de insertar productos y proveedores, porque los UUID los genera
          Supabase al insertar.
        - El todo-o-nada es por llamada a ``insert``, no global: si falla la
          inserción de ``historial_demanda``, las 3 tablas anteriores ya
          quedaron cargadas. Reintentar exige vaciar las tablas (ver el mensaje
          de :func:`_verificar_tablas_vacias`); por eso la validación previa
          cubre también las referencias entre archivos.
        - No modifica los DataFrames de entrada: cada ayudante devuelve copias.
    """
    directorio: Path = Path(data_dir)

    # Etapa 1: las tablas tienen que estar vacías. Va primero, antes de mirar
    # siquiera los archivos: si hay datos, la carga no se intenta.
    _verificar_tablas_vacias(supabase_client)

    # Etapa 2: leer y validar los 4 archivos, todo junto y antes de escribir:
    # un archivo inválido tiene que fallar sin haber insertado nada.
    productos: pd.DataFrame = _leer_archivo("productos", directorio)
    _validar_columnas(productos, COLUMNAS_PRODUCTOS, "productos")
    _validar_sin_nulos(productos, NO_NULAS_PRODUCTOS, "productos")
    _validar_sin_duplicados(productos, CLAVES_PRODUCTOS, "productos")

    proveedores: pd.DataFrame = _leer_archivo("proveedores", directorio)
    _validar_columnas(proveedores, COLUMNAS_PROVEEDORES, "proveedores")
    _validar_sin_nulos(proveedores, NO_NULAS_PROVEEDORES, "proveedores")
    _validar_sin_duplicados(proveedores, CLAVES_PROVEEDORES, "proveedores")

    relaciones: pd.DataFrame = _leer_archivo("producto_proveedor", directorio)
    _validar_columnas(relaciones, COLUMNAS_PRODUCTO_PROVEEDOR, "producto_proveedor")
    _validar_sin_nulos(relaciones, NO_NULAS_PRODUCTO_PROVEEDOR, "producto_proveedor")
    _validar_sin_duplicados(relaciones, CLAVES_PRODUCTO_PROVEEDOR, "producto_proveedor")

    historial: pd.DataFrame = _leer_archivo("historial_demanda", directorio)
    _validar_columnas(historial, COLUMNAS_HISTORIAL, "historial_demanda")
    _validar_sin_nulos(historial, NO_NULAS_HISTORIAL, "historial_demanda")
    _validar_sin_duplicados(historial, CLAVES_HISTORIAL, "historial_demanda")

    # Etapa 3: integridad referencial entre archivos, contra los nombres de los
    # propios CSV. Se adelanta aquí para no dejar productos y proveedores
    # insertados si una relación apunta a un nombre que no existe: eso
    # obligaría a vaciar las tablas para reintentar.
    _validar_referencias(
        relaciones,
        COLUMNA_PRODUCTO_NOMBRE,
        productos[COLUMNA_NOMBRE],
        "producto_proveedor",
        "productos",
    )
    _validar_referencias(
        relaciones,
        COLUMNA_PROVEEDOR_NOMBRE,
        proveedores[COLUMNA_NOMBRE],
        "producto_proveedor",
        "proveedores",
    )
    _validar_referencias(
        historial,
        COLUMNA_PRODUCTO_NOMBRE,
        productos[COLUMNA_NOMBRE],
        "historial_demanda",
        "productos",
    )

    # Etapa 4: las dos tablas sin claves foráneas, en orden de dependencias.
    conteos: dict[str, int] = {
        "productos": _insertar_tabla(supabase_client, "productos", productos),
        "proveedores": _insertar_tabla(supabase_client, "proveedores", proveedores),
    }

    # Etapa 5: una consulta por tabla referenciada para construir el mapa
    # {nombre: uuid} (los UUID recién ahora existen) y mapeo vectorizado con
    # pandas. Las columnas de nombre se descartan antes de insertar: no existen
    # en las tablas de destino.
    mapa_productos: dict[str, str] = _mapa_fks(
        supabase_client, "productos", COLUMNA_NOMBRE
    )
    mapa_proveedores: dict[str, str] = _mapa_fks(
        supabase_client, "proveedores", COLUMNA_NOMBRE
    )

    relaciones = _agregar_fk(
        relaciones,
        mapa_productos,
        COLUMNA_PRODUCTO_NOMBRE,
        COLUMNA_PRODUCTO_ID,
        "productos",
        "producto_proveedor",
        supabase_client,
    )
    relaciones = _agregar_fk(
        relaciones,
        mapa_proveedores,
        COLUMNA_PROVEEDOR_NOMBRE,
        COLUMNA_PROVEEDOR_ID,
        "proveedores",
        "producto_proveedor",
        supabase_client,
    )
    relaciones = relaciones.drop(
        columns=[COLUMNA_PRODUCTO_NOMBRE, COLUMNA_PROVEEDOR_NOMBRE]
    )

    historial = _agregar_fk(
        historial,
        mapa_productos,
        COLUMNA_PRODUCTO_NOMBRE,
        COLUMNA_PRODUCTO_ID,
        "productos",
        "historial_demanda",
        supabase_client,
    )
    historial = historial.drop(columns=[COLUMNA_PRODUCTO_NOMBRE])

    conteos["producto_proveedor"] = _insertar_tabla(
        supabase_client, "producto_proveedor", relaciones
    )
    conteos["historial_demanda"] = _insertar_tabla(
        supabase_client, "historial_demanda", historial
    )

    return conteos


def _verificar_tablas_vacias(supabase_client: "Client") -> None:
    """
    Verifica que las 4 tablas de datos estén vacías antes de insertar.

    Args:
        supabase_client: cliente de Supabase (``service_role``) ya configurado.

    Raises:
        RuntimeError: si alguna tabla de :data:`TABLAS_DATOS` tiene al menos una
            fila. El mensaje indica cuáles y sugiere el ``truncate`` que las
            vacía.

    Notas:
        - Solo lee: no borra ni sobrescribe nada. Vaciar las tablas es una
          decisión del operador, no del script.
        - Cada tabla se consulta con ``select("*").limit(1)``: alcanza con saber
          si hay alguna fila. Se selecciona ``"*"`` y no ``"id"`` porque
          ``producto_proveedor`` no tiene columna ``id`` (su primary key es
          compuesta: ``producto_id``, ``proveedor_id``); ``"*"`` sirve para las
          cuatro tablas por igual.
        - Las tablas de salida del motor (``recomendaciones`` y
          ``evaluaciones_criterios``) no se verifican porque este script no las
          escribe, pero sí conviene vaciarlas antes de recargar el dataset:
          ``recomendaciones.proveedor_id`` es ``on delete restrict`` y bloquea
          el borrado de un proveedor referenciado.
        - Es la primera etapa de :func:`cargar_dataset` a propósito: si hay
          datos, la carga no debe intentarse.
    """
    con_datos: list[str] = [
        tabla
        for tabla in TABLAS_DATOS
        if supabase_client.table(tabla).select("*").limit(1).execute().data
    ]
    if con_datos:
        raise RuntimeError(
            f"cargar_dataset: estas tablas ya tienen datos: "
            f"{', '.join(con_datos)}. El script no borra ni sobrescribe nada, "
            "así que hay que vaciarlas antes de recargar. En el SQL Editor de "
            f"Supabase:\n  {TRUNCATE_SUGERIDO}"
        )


def _leer_archivo(base_name: str, data_dir: Path) -> pd.DataFrame:
    """
    Lee un archivo del dataset, en CSV o en Excel.

    Busca ``base_name.csv`` y luego ``base_name.xlsx``, en ese orden de
    precedencia, dentro de ``data_dir``.

    Args:
        base_name: nombre del archivo sin extensión (``"productos"``).
        data_dir: directorio donde viven los archivos del dataset.

    Returns:
        DataFrame con las filas del archivo. Las columnas quedan como las
        infiere pandas: las fechas NO se parsean aquí (de eso se ocupa
        :func:`_insertar_tabla` antes de insertar).

    Raises:
        FileNotFoundError: si no existe ninguna de las dos extensiones.
        RuntimeError: si el archivo es ``.xlsx`` y falta ``openpyxl``.

    Notas:
        - El CSV se lee con ``index_col=False``: un CSV generado con
          ``DataFrame.to_csv()`` trae la primera columna sin nombre (el índice),
          y sin ese flag pandas la tomaría como índice y agregaría una columna
          espuria al dataset.
        - ``.xlsx`` necesita ``openpyxl``, que no está en
          ``backend/requirements.txt`` porque el MVP solo usa CSV; si falta, el
          error lo explica y ofrece la alternativa de exportar a CSV.
        - No valida columnas: de eso se ocupa :func:`_validar_columnas`, que
          recibe el nombre del archivo para el mensaje.
    """
    for extension in EXTENSIONES:
        ruta: Path = data_dir / f"{base_name}{extension}"
        if not ruta.exists():
            continue
        if extension == ".csv":
            return pd.read_csv(ruta, index_col=False)
        try:
            return pd.read_excel(ruta)
        except ImportError as error:
            raise RuntimeError(
                f"cargar_dataset: para leer '{ruta.name}' hace falta openpyxl "
                "(no está instalado). Instalalo con 'pip install openpyxl' o "
                f"exportá el archivo como '{base_name}.csv'."
            ) from error

    esperados: str = ", ".join(f"{base_name}{ext}" for ext in EXTENSIONES)
    raise FileNotFoundError(
        f"cargar_dataset: no se encontró '{base_name}' en '{data_dir}'. "
        f"Se esperaba uno de: {esperados}."
    )


def _validar_columnas(
    df: pd.DataFrame, columnas: tuple[str, ...], nombre: str
) -> None:
    """
    Valida que el DataFrame tenga todas las columnas requeridas.

    Args:
        df: DataFrame recién leído del archivo.
        columnas: columnas que debe tener el archivo.
        nombre: nombre del archivo, para el mensaje de error.

    Raises:
        ValueError: si falta alguna columna. El mensaje lista las que faltan y
            las que se esperaban.

    Notas:
        - Comprueba solo la presencia, en cualquier orden. Las columnas de más
          no se rechazan aquí, pero :func:`_insertar_tabla` sí exige que el
          DataFrame tenga exactamente las columnas de la tabla de destino (ver
          :data:`COLUMNAS_TABLA`).
        - No comprueba tipos: si una columna trae texto donde la base espera un
          número, el error lo da Postgres al insertar.
    """
    faltantes: list[str] = [
        columna for columna in columnas if columna not in df.columns
    ]
    if faltantes:
        raise ValueError(
            f"cargar_dataset: al archivo '{nombre}' le faltan "
            f"{len(faltantes)} columna(s) requerida(s): {', '.join(faltantes)}. "
            f"Se esperaban: {', '.join(columnas)}."
        )


def _validar_sin_nulos(
    df: pd.DataFrame, columnas: tuple[str, ...], nombre: str
) -> None:
    """
    Valida que las columnas obligatorias no tengan nulos.

    Args:
        df: DataFrame del archivo, ya con las columnas verificadas.
        columnas: columnas que en la tabla de destino son ``not null``.
        nombre: nombre del archivo, para el mensaje de error.

    Raises:
        ValueError: si alguna de las columnas tiene nulos. El mensaje reporta
            **todas** las columnas afectadas, con la cantidad de filas y las
            líneas del archivo (numeradas como se ven en el editor, contando el
            encabezado), para corregir el origen de una sola pasada.

    Notas:
        - La línea se calcula por posición de la fila (``enumerate`` sobre la
          máscara de nulos), no por el índice del DataFrame: así el número no
          depende de que el índice sea un RangeIndex.
        - Las columnas que en la tabla admiten nulos no se pasan aquí: en este
          dataset un nulo ahí significa "sin dato" (por ejemplo, un producto sin
          descuento por volumen) y se inserta como ``null``.
        - No valida tipos ni rangos: los rangos (``>= 0``, ``between 0 and
          100``) los aplica la base con sus restricciones ``check``.
    """
    con_nulos: dict[str, list[int]] = {}
    for columna in columnas:
        nulos = df[columna].isna().to_numpy()
        filas: list[int] = [
            indice + 2 for indice, es_nulo in enumerate(nulos) if es_nulo
        ]
        if filas:
            con_nulos[columna] = filas

    if con_nulos:
        partes: list[str] = []
        for columna, filas in con_nulos.items():
            lineas: str = ", ".join(str(fila) for fila in filas)
            partes.append(f"{columna} -> {len(filas)} fila(s) (línea(s) {lineas})")
        total: int = sum(len(filas) for filas in con_nulos.values())
        raise ValueError(
            f"cargar_dataset: el archivo '{nombre}' tiene {total} celda(s) "
            f"nula(s) en columnas que no admiten nulos "
            f"({', '.join(columnas)}): {'; '.join(partes)}."
        )


def _validar_sin_duplicados(
    df: pd.DataFrame, columnas: tuple[str, ...], nombre: str
) -> None:
    """
    Valida que las claves del archivo no estén repetidas.

    Args:
        df: DataFrame del archivo.
        columnas: columnas que forman la clave (el nombre del producto, el par
            producto-proveedor, el par producto-periodo).
        nombre: nombre del archivo, para el mensaje de error.

    Raises:
        ValueError: si hay filas con la misma clave. El mensaje lista las líneas
            y los valores repetidos.

    Notas:
        - Es una validación agregada a las del pedido, por dos motivos. En
          ``productos`` y ``proveedores`` el nombre no es ``unique`` en el
          schema, pero un nombre repetido hace ambigua la resolución de la
          clave foránea: el mapa {nombre: uuid} no puede elegir uno. En
          ``producto_proveedor`` e ``historial_demanda`` la clave coincide con
          la PK y con el UNIQUE de la tabla, así que el duplicado lo rechazaría
          Postgres a mitad de la carga y el dataset quedaría a medias.
        - Se reportan todas las filas con ``keep=False``: las repetidas, no solo
          las segundas ocurrencias.
        - La línea se calcula por posición de la fila, no por el índice del
          DataFrame (misma convención que :func:`_validar_sin_nulos`).
    """
    mascara = df.duplicated(subset=list(columnas), keep=False).to_numpy()
    filas: list[int] = [
        indice + 2 for indice, repetida in enumerate(mascara) if repetida
    ]
    if filas:
        claves: str = ", ".join(
            " | ".join(str(valor) for valor in valores)
            for valores in df.loc[mascara, list(columnas)].itertuples(index=False)
        )
        raise ValueError(
            f"cargar_dataset: el archivo '{nombre}' tiene {len(filas)} fila(s) "
            f"con la clave ({', '.join(columnas)}) repetida (líneas "
            f"{', '.join(str(fila) for fila in filas)}): {claves}. "
            "Cada clave tiene que ser única."
        )


def _validar_referencias(
    df: pd.DataFrame,
    columna: str,
    valores_validos: pd.Series,
    nombre: str,
    tabla_destino: str,
) -> None:
    """
    Valida que los nombres de una columna existan en otro archivo del dataset.

    Args:
        df: DataFrame que referencia (``producto_proveedor`` o
            ``historial_demanda``).
        columna: columna con los nombres a verificar (``producto_nombre`` o
            ``proveedor_nombre``).
        valores_validos: serie con los nombres que existen, tomada del archivo
            referenciado (``productos["nombre"]`` o ``proveedores["nombre"]``).
        nombre: nombre del archivo que referencia, para el mensaje de error.
        tabla_destino: tabla donde deberían existir esos nombres (``productos``
            o ``proveedores``).

    Raises:
        ValueError: si hay nombres que no están en ``valores_validos``. El
            mensaje lista todos.

    Notas:
        - Se valida contra los nombres de los CSV, no contra la base: en este
          punto de la carga las tablas referenciadas todavía están vacías (el
          script exige que lo estén) y los archivos se insertan recién en la
          etapa siguiente.
        - Sirve para no dejar la carga a medias: si la referencia rota se
          detectara durante la inserción de las relaciones, productos y
          proveedores ya estarían cargados y, como las tablas no pueden tener
          datos, reintentar exigiría un ``truncate`` manual.
        - Los valores se comparan como texto (``str``) para que el mensaje sea
          legible aunque la columna haya llegado con otro dtype.
    """
    validos: set[str] = {str(valor) for valor in valores_validos}
    huerfanos: list[str] = sorted(
        {str(valor) for valor in df[columna] if str(valor) not in validos}
    )
    if huerfanos:
        raise ValueError(
            f"cargar_dataset: en el archivo '{nombre}' hay {len(huerfanos)} "
            f"valor(es) de la columna '{columna}' que no están en "
            f"'{tabla_destino}.csv': {', '.join(huerfanos)}. El nombre tiene "
            f"que coincidir exactamente con el del archivo "
            f"'{tabla_destino}.csv'."
        )


def _insertar_tabla(
    supabase_client: "Client", tabla: str, df: pd.DataFrame
) -> int:
    """
    Normaliza un DataFrame y lo inserta completo en una tabla de Supabase.

    Args:
        supabase_client: cliente de Supabase (``service_role``) ya configurado.
        tabla: nombre de la tabla de destino; tiene que estar en
            :data:`COLUMNAS_TABLA`.
        df: DataFrame ya con las columnas de la tabla (claves foráneas resueltas
            y columnas de nombre descartadas). No se modifica: se trabaja sobre
            una copia.

    Returns:
        Cantidad de filas insertadas (``len(df)``). El ``insert`` de PostgREST
        es atómico por llamada: o se insertan todas o ninguna.

    Raises:
        ValueError: si el DataFrame no tiene exactamente las columnas de
            :data:`COLUMNAS_TABLA` para ``tabla``, o si ``periodo`` trae valores
            que no se pueden interpretar como fecha.
        Exception: cualquier error de la API de Supabase se propaga tal cual.

    Notas:
        - Normaliza los tipos antes de insertar: ``periodo`` a ISO
          (``YYYY-MM-DD``) y las columnas de :data:`COLUMNAS_ENTERAS` a ``int``
          de Python. Una columna entera con nulos se lee como ``float`` y
          PostgREST rechazaría ``lead_time_dias: 7.0``.
        - Reemplaza los nulos (``NaN``/``NaT``/``NA``) por ``None`` para que
          PostgREST inserte ``NULL`` y no la cadena ``"NaN"``.
        - Convierte los escalares de numpy a tipos nativos (``int``, ``float``,
          ``str``) porque ``json`` no los sabe serializar.
        - Reordena las columnas al orden de :data:`COLUMNAS_TABLA`: no cambia el
          resultado, pero hace la carga determinista.
    """
    esperadas: tuple[str, ...] = COLUMNAS_TABLA[tabla]
    faltantes: list[str] = [c for c in esperadas if c not in df.columns]
    sobrantes: list[str] = [c for c in df.columns if c not in esperadas]
    if faltantes or sobrantes:
        raise ValueError(
            f"cargar_dataset: el DataFrame para '{tabla}' no tiene exactamente "
            f"las columnas de la tabla. Faltan: "
            f"{', '.join(faltantes) or 'ninguna'}; sobran: "
            f"{', '.join(sobrantes) or 'ninguna'}. Se esperaban: "
            f"{', '.join(esperadas)}."
        )

    resultado: pd.DataFrame = df.loc[:, list(esperadas)].copy()

    # periodo -> ISO. errors="raise" hace fallar aquí una fecha inválida, con el
    # nombre de la tabla, y no más tarde en la API.
    if COLUMNA_PERIODO in resultado.columns:
        try:
            resultado[COLUMNA_PERIODO] = pd.to_datetime(
                resultado[COLUMNA_PERIODO], errors="raise"
            ).dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"cargar_dataset: la columna '{COLUMNA_PERIODO}' de '{tabla}' "
                f"tiene valores que no son fechas válidas: {error}"
            ) from error

    # Columnas 'integer' de la base: a int de Python (None donde haya nulo).
    for columna in COLUMNAS_ENTERAS.get(tabla, ()):
        numeros = pd.to_numeric(resultado[columna], errors="raise")
        resultado[columna] = pd.Series(
            [None if pd.isna(valor) else int(valor) for valor in numeros],
            index=resultado.index,
        )

    # DataFrame -> list[dict] con nulos en None y escalares nativos de Python.
    registros: list[dict[str, object]] = []
    for fila in resultado.to_dict(orient="records"):
        registro: dict[str, object] = {}
        for clave, valor in fila.items():
            if pd.isna(valor):
                registro[clave] = None
            elif hasattr(valor, "item"):
                registro[clave] = valor.item()
            else:
                registro[clave] = valor
        registros.append(registro)

    supabase_client.table(tabla).insert(registros).execute()
    return len(registros)


def _mapa_fks(
    supabase_client: "Client", tabla: str, columna_nombre: str
) -> dict[str, str]:
    """
    Construye el mapa {nombre: uuid} de una tabla referenciada.

    Args:
        supabase_client: cliente de Supabase (``service_role``) ya configurado.
        tabla: tabla referenciada (``"productos"`` o ``"proveedores"``).
        columna_nombre: columna con el nombre legible (``"nombre"``), que es la
            que usan los archivos para referenciar la fila.

    Returns:
        dict que mapea cada valor de ``columna_nombre`` a su ``id`` (uuid).

    Raises:
        ValueError: si hay valores repetidos en ``columna_nombre``: no se pueden
            resolver a un único uuid. Se listan todos los repetidos.
        Exception: cualquier error de la API de Supabase se propaga tal cual.

    Notas:
        - Una sola consulta para toda la tabla (no una por fila): alcanza porque
          el dataset es chico. El mapeo posterior, en :func:`_agregar_fk`, es
          vectorizado con pandas.
        - Se leen ``id`` y ``columna_nombre`` juntas, sin depender del orden de
          las filas.
        - El ``schema`` no impide nombres repetidos (``productos.nombre`` y
          ``proveedores.nombre`` no son ``unique``); un nombre repetido haría
          ambigua la resolución de la clave foránea, así que se comprueba aquí.
    """
    respuesta = (
        supabase_client.table(tabla).select(f"id,{columna_nombre}").execute()
    )
    filas: list[dict[str, object]] = respuesta.data or []

    conteo: dict[str, int] = {}
    mapa: dict[str, str] = {}
    for fila in filas:
        nombre: str = str(fila[columna_nombre])
        mapa[nombre] = str(fila["id"])
        conteo[nombre] = conteo.get(nombre, 0) + 1

    repetidos: list[str] = sorted(n for n, veces in conteo.items() if veces > 1)
    if repetidos:
        raise ValueError(
            f"cargar_dataset: la tabla '{tabla}' tiene {len(repetidos)} "
            f"nombre(s) repetido(s) en la columna '{columna_nombre}': "
            f"{', '.join(repetidos)}. Un nombre repetido no se puede resolver a "
            "un único uuid; cada nombre tiene que ser único para poder mapear "
            "la clave foránea."
        )
    return mapa



def _agregar_fk(
    df: pd.DataFrame,
    mapa: dict[str, str],
    columna_nombre: str,
    columna_id: str,
    tabla_destino: str,
    nombre: str,
    supabase_client: "Client",
) -> pd.DataFrame:
    """
    Agrega la clave foránea (uuid) a partir de la columna de nombre.

    Toma la columna ``columna_nombre`` del DataFrame, la resuelve contra ``mapa``
    y escribe el uuid en una columna nueva ``columna_id``. La columna de nombre
    se conserva: el llamador la descarta recién cuando resolvió todas las claves
    foráneas del DataFrame.

    Args:
        df: DataFrame que referencia (``producto_proveedor`` o
            ``historial_demanda``).
        mapa: dict {nombre: uuid} de la tabla referenciada, construido por
            :func:`_mapa_fks`.
        columna_nombre: columna del DataFrame con los nombres a resolver
            (``producto_nombre`` o ``proveedor_nombre``).
        columna_id: columna de la tabla de destino que se agrega al DataFrame
            (``producto_id`` o ``proveedor_id``).
        tabla_destino: tabla referenciada (``productos`` o ``proveedores``); se
            usa para diagnosticar los nombres que no se resuelven.
        nombre: nombre del archivo que referencia, para el mensaje de error.
        supabase_client: cliente de Supabase (``service_role``), para consultar
            ``tabla_destino`` solo por los nombres que no se pudieron resolver.

    Returns:
        Copia de ``df`` con la columna ``columna_id`` agregada.

    Raises:
        ValueError: si algún valor de ``columna_nombre`` no está en ``mapa`` (o
            es ambiguo en ``tabla_destino``). El mensaje lista los nombres y las
            líneas afectadas.
        Exception: cualquier error de la API de Supabase se propaga tal cual.

    Notas:
        - El mapeo es vectorizado (``Series.map``), no un ``join``: mantiene el
          orden y el índice de ``df`` (necesario para reportar las líneas).
        - No modifica el DataFrame de entrada: parte de una copia.
        - La consulta a ``tabla_destino`` ocurre **solo** en el caso de error,
          para distinguir "el nombre no existe" de "el nombre es ambiguo
          (repetido)"; el camino feliz no toca la base.
        - La línea se calcula por posición de la fila, no por el índice del
          DataFrame (misma convención que :func:`_validar_sin_nulos`).
    """
    resultado: pd.DataFrame = df.copy()
    resultado[columna_id] = resultado[columna_nombre].map(mapa)

    sin_resolver = resultado[columna_id].isna()
    if bool(sin_resolver.any()):
        faltantes: list[str] = sorted(
            {str(valor) for valor in resultado.loc[sin_resolver, columna_nombre]}
        )
        filas: list[int] = [
            posicion + 2
            for posicion, malo in enumerate(sin_resolver.to_numpy())
            if malo
        ]

        # Diagnóstico opcional: ¿el nombre no existe en la tabla o está repetido?
        detalle: str = ""
        try:
            respuesta = (
                supabase_client.table(tabla_destino)
                .select(columna_nombre)
                .in_(columna_nombre, faltantes)
                .execute()
            )
            conteo: dict[str, int] = {}
            for fila in respuesta.data or []:
                clave: str = str(fila[columna_nombre])
                conteo[clave] = conteo.get(clave, 0) + 1
            ambiguos: list[str] = sorted(
                n for n in faltantes if conteo.get(n, 0) > 1
            )
            if ambiguos:
                detalle = (
                    f" Estos nombres están repetidos en '{tabla_destino}' y no "
                    f"se pueden resolver a un único uuid: {', '.join(ambiguos)}."
                )
        except Exception:  # noqa: BLE001 - el diagnóstico es opcional
            detalle = ""

        raise ValueError(
            f"cargar_dataset: en el archivo '{nombre}' hay {len(filas)} fila(s) "
            f"con la columna '{columna_nombre}' que no se pudieron resolver a un "
            f"uuid de '{tabla_destino}' (líneas "
            f"{', '.join(str(fila) for fila in filas)}): "
            f"{', '.join(faltantes)}.{detalle}"
        )

    return resultado

