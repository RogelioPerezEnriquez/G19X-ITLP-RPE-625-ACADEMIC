"""Demo end-to-end del flujo completo: motor OR, recomendaciones y rubrica.

Proposito
---------
Correr de punta a punta el pipeline del MVP contra los datos reales del seed en
Supabase: generar las recomendaciones de compra, guardarlas en la tabla
``recomendaciones``, cruzar los UUID que Supabase genera con las recomendaciones
del motor y aplicar la rubrica de 6 criterios (MVP.md seccion 10), guardando el
resultado en ``evaluaciones_criterios``. Es el flujo que une
``src.recomendador`` con ``src.evaluador``, que hasta ahora solo se habian
probado por separado.

Como correrlo
-------------
Desde la raiz del proyecto::

    python scripts/demo_flujo_completo.py

El script carga las variables de ``.env`` (en la raiz) y usa ``SUPABASE_URL`` y
``SUPABASE_SERVICE_ROLE_KEY``. La ``service_role key`` es necesaria porque, si se
confirma el guardado, el script escribe en ``recomendaciones`` y en
``evaluaciones_criterios`` (las dos tienen RLS habilitado con politicas de solo
lectura, asi que la ``anon key`` no alcanza para guardar).

Que hace
--------
1. Carga ``.env`` desde la raiz del proyecto (robusto ante el cwd, porque la
   ruta se deriva de ``__file__``).
2. Crea el cliente de Supabase con la ``service_role key`` y comprueba la
   conectividad con una lectura minima.
3. Cuenta las recomendaciones que ya hay en la tabla y, si hay alguna, avisa y
   pide confirmacion antes de escribir nada (ver "Limitacion conocida").
4. Paso 1: ``generar_recomendaciones(supabase)`` (lectura de las cuatro tablas +
   motor OR).
5. Muestra el reporte de detalle (ver "Formato del reporte"): encabezado, cantidad
   de recomendaciones generadas, una fila por producto con su proveedor y sus
   numeros, y el resumen agregado. El reporte se imprime siempre, se guarde o no,
   porque sale del DataFrame que devuelve el motor y no de la base.
6. Pregunta ``Desea guardar las recomendaciones en Supabase? [S/N]``. El default
   es "N": si el usuario solo presiona Enter (respuesta vacia) no se guarda nada.
   Solo una respuesta explicita afirmativa ("s", "si", "y", "yes") hace que se
   guarde. Si no se confirma, no se inserta ni se evalua nada y el flujo termina
   con codigo 0 (ver "Si no se guarda, no hay evaluaciones").
7. Paso 2: ``guardar_recomendaciones(supabase, recomendaciones)``, que devuelve
   las filas insertadas con su UUID.
8. Paso 3: cruza los UUID con las recomendaciones del motor. Toma ``id`` y
   ``producto_id`` de lo guardado, renombra ``id`` a ``recomendacion_id`` y hace
   ``merge`` con las recomendaciones por ``producto_id`` (``how="inner"``).
   Verifica que el resultado tenga exactamente una fila por recomendacion.
9. Paso 4: ``evaluar_y_guardar(supabase, recomendaciones_con_id)`` (rubrica de 6
   criterios + INSERT en ``evaluaciones_criterios``).
10. Imprime los conteos de cada etapa y, al final, el conteo leido de vuelta de la
    base y la confirmacion de la escritura (solo si se guardo).

Por que hace falta cruzar los UUID
----------------------------------
El motor produce las recomendaciones sin ``id`` (todavia no existen) y el
evaluador necesita ``recomendacion_id`` con el UUID de la recomendacion ya
persistida. Ese UUID lo genera Supabase al insertar y vuelve en la respuesta del
``insert``, asi que hay que cruzar esa respuesta con el DataFrame del motor. El
cruce es 1:1 porque el motor emite una recomendacion por producto valido, y se
hace por ``producto_id`` porque varias columnas que el evaluador necesita
(``stock_actual``, ``costo_total_pedido`` y ``score_proveedor``, entre otras) no
se guardan en la tabla ``recomendaciones``: se toman del DataFrame del motor.

Limitacion conocida
-------------------
Este demo asume que se corre sobre una tabla ``recomendaciones`` vacia, y solo
avisa (no limpia) si no lo esta. Con corridas anteriores:

- El cruce de UUID de esta ejecucion no se mezcla con ellas: se hace contra las
  filas que devuelve el ``insert`` de esta corrida, que son exactamente las
  recomendaciones recien creadas.
- Lo que si se acumula es el historico: las dos tablas guardan las filas de
  todas las corridas y las recomendaciones viejas quedan sin evaluaciones
  nuevas. Para analizar, hay que filtrar por ``fecha_generacion`` o por
  ``estado``.
- Si el cruce se hiciera contra una relectura de la tabla completa (en lugar de
  la respuesta del ``insert``), cada producto con varias corridas multiplicaria
  las filas y las evaluaciones quedarian asociadas a la recomendacion
  equivocada. El paso 3 aborta con un mensaje claro si el conteo no cuadra, en
  lugar de escribir evaluaciones cruzadas.

Si no se guarda, no hay evaluaciones
------------------------------------
El reporte de detalle se arma con el DataFrame que devuelve el motor, asi que se
puede mostrar sin escribir nada en Supabase. Las evaluaciones no: la rubrica
necesita el ``recomendacion_id`` (el UUID que Supabase asigna al insertar la
recomendacion), porque el motor produce las recomendaciones sin ``id``. Por eso
responder que no a la pregunta de guardado no solo evita el INSERT en
``recomendaciones``: tambien deja sin evaluar las recomendaciones generadas (la
tabla ``evaluaciones_criterios`` referencia la recomendacion persistida por clave
foranea). Es una limitacion del diseno, no algo que este flujo pueda rodear: para
ver las evaluaciones hay que correrlo de nuevo y confirmar el guardado.

Formato del reporte
-------------------
Texto plano, sin emojis ni colores ANSI (pensado para Windows). El orden es:

1. Encabezado (titulo enmarcado con ``=``).
2. ``Recomendaciones generadas: <n>``.
3. Tabla de detalle con una fila por producto: ``producto``, ``proveedor``,
   ``clase_abc``, ``clase_xyz``, ``urgencia``, ``stock_actual``,
   ``punto_reorden``, ``cantidad_recomendada``, ``ahorro_neto_estimado`` y
   ``score_proveedor``. La tabla se arma con ``|`` y ``-``.
4. Resumen agregado: conteo de recomendaciones por urgencia, recomendaciones con
   ``'Ahorro detectado'`` y suma de ``ahorro_neto_estimado``.
5. Pregunta de guardado, y al final la confirmacion de la escritura en Supabase o
   el mensaje de cancelacion si no se guardo (con la aclaracion de que, en ese
   caso, tampoco se generaron evaluaciones).

Las secciones 1 a 4 salen antes de la pregunta: el reporte de detalle es
justamente lo que se mira para decidir si vale la pena guardar.

Que NO hace
-----------
- No modifica el motor, el recomendador, el evaluador ni ningun otro archivo del
  repositorio.
- No borra ni limpia recomendaciones ni evaluaciones existentes: solo inserta
  filas nuevas.
- No escribe nada en Supabase si el usuario no confirma el guardado (y en ese caso
  tampoco evalua: ver "Si no se guarda, no hay evaluaciones").
- No inserta datos de prueba en ``productos``/``proveedores`` (para eso estan
  ``db/seed_sintetico.sql`` y ``scripts/verificar_*.py``).
- No usa colores ANSI ni emojis: la salida es texto plano pensado para Windows.

Decision de import (``sys.path``)
---------------------------------
``backend/src/recomendador.py`` y ``backend/src/evaluador.py`` importan los
modulos del motor con rutas absolutas (``from src.motor.abc import ...``), de
modo que su paquete padre ``src`` tiene que ser importable. Agregar
``backend/src`` al ``sys.path`` no alcanza: ``src`` quedaria fuera del path y el
import interno del motor fallaria con ``ModuleNotFoundError``. Por eso se agrega
``backend`` (el padre de ``src``) y se importa como ``src.recomendador`` y
``src.evaluador``, que es exactamente como lo hacen los tests
(``backend/tests/``). El script importa ademas ``ESTADO_AHORRO`` desde
``src.motor.ahorro`` (la etiqueta del criterio 6) y ``ORDEN_URGENCIA`` desde
``src.recomendador`` para armar el resumen del reporte sin repetir los textos a
mano, igual que ``scripts/demo_recomendador.py``.

Contrato de errores
-------------------
- ``.env`` ausente, cliente no creado o sin conexion: mensaje claro y salida con
  codigo 1.
- Fallo en cualquiera de los cuatro pasos: se informa que paso fallo y la causa
  (tipo y mensaje de la excepcion) y se sale con codigo 1. No se captura en
  silencio ni se sigue con datos a medias.
- Tabla ``recomendaciones`` con filas y el usuario no confirma: no se escribe
  nada y se sale con codigo 0 (no es un error).
- El usuario responde que no a la pregunta de guardado (o solo presiona Enter):
  no se escribe nada, no se generan evaluaciones y se sale con codigo 0 (no es un
  error). El reporte de detalle se imprime igual.
- Sin recomendaciones que guardar (ningun producto valido): no se escribe nada y
  se sale con codigo 0.
- Conteos finales que no cuadran: se reporta y se sale con codigo 1.
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
from src.evaluador import (  # noqa: E402
    ORDEN_CRITERIOS,
    TABLA_EVALUACIONES,
    evaluar_y_guardar,
)
from src.motor.ahorro import ESTADO_AHORRO  # noqa: E402
from src.recomendador import (  # noqa: E402
    ORDEN_URGENCIA,
    generar_recomendaciones,
    guardar_recomendaciones,
)

# Ancho de las lineas separadoras del reporte.
ANCHO_REPORTE: int = 78

# Respuestas afirmativas aceptadas al preguntar si se continua.
RESPUESTAS_AFIRMATIVAS: frozenset[str] = frozenset({"s", "si", "y", "yes"})

# Evaluaciones que produce la rubrica por recomendacion: una fila por
# (recomendacion_id, criterio). Se deriva de ORDEN_CRITERIOS (fuente unica de
# verdad del evaluador) en lugar de escribir un 6 a mano.
EVALUACIONES_POR_RECOMENDACION: int = len(ORDEN_CRITERIOS)

# Nombres de las tablas que escribe el flujo.
TABLA_RECOMENDACIONES: str = "recomendaciones"


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


def _imprimir_cabecera(titulo: str) -> None:
    """Imprime un titulo enmarcado con ``=`` (texto plano, sin ANSI)."""
    print()
    print("=" * ANCHO_REPORTE)
    print(titulo)
    print("=" * ANCHO_REPORTE)


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
    """Imprime el encabezado del reporte y la tabla de detalle por producto.

    La tabla tiene una fila por recomendacion generada, con lo que hace falta para
    verificar que un cambio de configuracion movio los resultados: el proveedor
    elegido, las clases ABC/XYZ, la urgencia, el stock contra el punto de reorden,
    la cantidad recomendada, el ahorro neto estimado y el score del proveedor.

    Args:
        recomendaciones: DataFrame devuelto por
            :func:`src.recomendador.generar_recomendaciones`.
    """
    _imprimir_cabecera("REPORTE DE RECOMENDACIONES DE COMPRA")
    print(f"Recomendaciones generadas: {len(recomendaciones)}")
    print()

    if recomendaciones.empty:
        print("No hay recomendaciones: ningun producto cumple los criterios minimos")
        print("(al menos 2 periodos de historial, proveedor asociado y CV calculable).")
        return

    encabezados: list[str] = [
        "producto",
        "proveedor",
        "clase_abc",
        "clase_xyz",
        "urgencia",
        "stock_actual",
        "punto_reorden",
        "cantidad_recomendada",
        "ahorro_neto_estimado",
        "score_proveedor",
    ]
    filas: list[list[str]] = [
        [
            str(fila["nombre"]),
            str(fila["proveedor_nombre"]),
            str(fila["clase_abc"]),
            str(fila["clase_xyz"]),
            str(fila["urgencia"]),
            _formato_numero(float(fila["stock_actual"])),
            _formato_numero(float(fila["punto_reorden"])),
            _formato_numero(float(fila["cantidad_recomendada"])),
            _formato_numero(float(fila["ahorro_neto_estimado"])),
            _formato_numero(float(fila["score_proveedor"])),
        ]
        for _, fila in recomendaciones.iterrows()
    ]
    _imprimir_tabla(encabezados, filas)
    print()
    print("Leyenda: clase_abc/clase_xyz = clasificacion del producto; urgencia")
    print("comparada contra stock_seguridad (Critico) y punto_reorden (Atencion).")


def _imprimir_resumen(recomendaciones: pd.DataFrame) -> None:
    """Imprime el resumen agregado (urgencia, ahorro y suma de ahorro neto).

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


def _contar_recomendaciones_existentes(supabase: Client) -> int:
    """Cuenta las recomendaciones que ya hay en la tabla (0 si esta vacia).

    Args:
        supabase: cliente de Supabase ya configurado.

    Returns:
        Cantidad de filas de ``recomendaciones``. Se pide el conteo exacto con
        ``count="exact"`` y ``limit(1)``, de modo que no se descarga la tabla
        entera. Si el cliente no devolviera el conteo, se usa el largo de ``data``
        (que con ``limit(1)`` alcanza para saber que la tabla no esta vacia).

    Raises:
        Exception: cualquier error de la API se propaga al llamador, que lo
            reporta con su causa.
    """
    respuesta = (
        supabase.table(TABLA_RECOMENDACIONES)
        .select("id", count="exact")
        .limit(1)
        .execute()
    )
    if respuesta.count is not None:
        return int(respuesta.count)
    return len(respuesta.data or [])


def _confirmar_continuar(existentes: int) -> bool:
    """Avisa que la tabla ya tiene filas y pregunta si se quiere seguir.

    Args:
        existentes: cantidad de recomendaciones que ya habia en la tabla.

    Returns:
        ``True`` solo si el usuario responde que si; ``False`` en cualquier otra
        respuesta o si no hay entrada estandar disponible (por ejemplo, cuando el
        script se corre sin consola interactiva).

    Notas:
        El aviso incluye la limitacion: el cruce de UUID de esta corrida usa solo
        las filas que devuelve su propio ``insert``, pero el historico se acumula
        y las recomendaciones viejas quedan sin evaluaciones nuevas.
    """
    print()
    print("-" * ANCHO_REPORTE)
    print("ATENCION: la tabla 'recomendaciones' no esta vacia.")
    print("-" * ANCHO_REPORTE)
    print(f"Ya hay {existentes} recomendaciones guardadas. Esta corrida agregara")
    print("filas nuevas (una por producto recomendado) y sus evaluaciones, pero no")
    print("toca las anteriores.")
    print()
    print("Limitacion: el cruce de UUID se hace contra la respuesta del insert de")
    print("esta corrida, asi que no se mezcla con las filas viejas; lo que se")
    print("acumula es el historico (las recomendaciones anteriores quedan sin")
    print("evaluaciones nuevas) y para analizar hay que filtrar por")
    print("'fecha_generacion' o 'estado'.")
    print()
    print("Recomendado: correr este demo sobre una tabla vacia.")
    print()

    try:
        respuesta = input("Desea continuar de todas formas? [S/N]: ")
    except EOFError:
        print("Sin entrada estandar disponible: no se hizo nada.")
        return False
    return respuesta.strip().lower() in RESPUESTAS_AFIRMATIVAS


def _preguntar_guardar() -> bool:
    """Pregunta si se quieren guardar las recomendaciones en Supabase.

    El default es "no": si el usuario solo presiona Enter (respuesta vacia) no se
    guarda nada. Solo cuenta como afirmativa una respuesta explicita ("s", "si",
    "y", "yes", sin importar mayusculas/minusculas y espacios alrededor).

    Returns:
        ``True`` solo si el usuario responde afirmativamente; ``False`` en
        cualquier otra respuesta o si no hay entrada estandar disponible (por
        ejemplo, cuando el script se corre sin consola interactiva).

    Notas:
        Si no hay entrada estandar, se asume "no" y no se escribe nada: es el
        default seguro (una corrida no interactiva, como la de un CI, no debe
        escribir en la base por accidente).
    """
    try:
        respuesta = input("Desea guardar las recomendaciones en Supabase? [S/N]: ")
    except EOFError:
        print("Sin entrada estandar disponible: no se guardo nada.")
        return False
    return respuesta.strip().lower() in RESPUESTAS_AFIRMATIVAS


def _recomendaciones_con_id(
    recomendaciones: pd.DataFrame,
    guardadas: pd.DataFrame,
) -> pd.DataFrame:
    """Cruza los UUID recien guardados con las recomendaciones del motor.

    Args:
        recomendaciones: DataFrame devuelto por
            :func:`src.recomendador.generar_recomendaciones` (una fila por
            producto, sin ``recomendacion_id``).
        guardadas: DataFrame devuelto por
            :func:`src.recomendador.guardar_recomendaciones` (las filas
            insertadas, con ``id`` y ``producto_id``).

    Returns:
        Copia de ``recomendaciones`` con la columna ``recomendacion_id`` (el UUID
        de la recomendacion persistida), con una fila por recomendacion. Es la
        entrada que espera :func:`src.evaluador.evaluar_y_guardar`.

    Raises:
        ValueError: si a ``guardadas`` le faltan las columnas ``id`` o
            ``producto_id``; si algun UUID viene nulo o vacio; si la respuesta del
            ``insert`` trae un ``producto_id`` repetido; o si el cruce no cubre
            exactamente las recomendaciones generadas. Los dos ultimos casos
            significan que no se puede asociar cada evaluacion a la recomendacion
            correcta, asi que se aborta en lugar de escribir filas cruzadas.
    """
    faltantes: list[str] = [
        columna for columna in ("id", "producto_id") if columna not in guardadas.columns
    ]
    if faltantes:
        raise ValueError(
            "las recomendaciones guardadas no traen las columnas necesarias para "
            f"cruzar los UUID; faltan: {', '.join(faltantes)}."
        )

    con_id: pd.DataFrame = guardadas[["id", "producto_id"]].rename(
        columns={"id": "recomendacion_id"}
    )
    ids: pd.Series = con_id["recomendacion_id"]
    if ids.isna().any() or (ids.astype(str).str.strip() == "").any():
        raise ValueError(
            "Supabase no devolvio un UUID valido para alguna recomendacion; sin "
            "'recomendacion_id' el INSERT de las evaluaciones fallaria por clave "
            "foranea."
        )

    # El cruce tiene que ser 1:1. Se verifica por los dos lados: un producto
    # repetido en la respuesta del insert (o una recomendacion sin UUID) haria
    # que las evaluaciones se asociaran a la recomendacion equivocada, y el
    # conteo total por si solo no lo detecta (dos filas de un producto y ninguna
    # de otro suman lo mismo que un cruce correcto).
    if con_id["producto_id"].duplicated().any():
        repetidos = con_id.loc[con_id["producto_id"].duplicated(), "producto_id"]
        raise ValueError(
            "la respuesta del INSERT trae productos repetidos "
            f"({len(repetidos)} repeticiones: {', '.join(map(str, repetidos))}). "
            "El motor emite una recomendacion por producto, asi que hay filas "
            "duplicadas en la tabla: limpie 'recomendaciones' o filtre por "
            "'fecha_generacion'/'estado' antes de continuar, porque no se puede "
            "saber a que recomendacion corresponden las evaluaciones."
        )

    resultado: pd.DataFrame = recomendaciones.merge(
        con_id, on="producto_id", how="inner"
    )

    sin_uuid: list = sorted(
        set(recomendaciones["producto_id"]) - set(resultado["producto_id"]), key=str
    )
    if sin_uuid or len(resultado) != len(recomendaciones):
        raise ValueError(
            f"el cruce por 'producto_id' cubre {len(resultado)} de "
            f"{len(recomendaciones)} recomendaciones (sin UUID: "
            f"{len(sin_uuid)}): la respuesta del INSERT no trae una fila por "
            "recomendacion generada, asi que las evaluaciones quedarian "
            "incompletas o cruzadas."
        )

    return resultado


def _contar_evaluaciones(supabase: Client, recomendacion_ids: list) -> int | None:
    """Cuenta en la base las evaluaciones de estas recomendaciones.

    Args:
        supabase: cliente de Supabase ya configurado.
        recomendacion_ids: UUID de las recomendaciones de esta corrida.

    Returns:
        Cantidad de filas de ``evaluaciones_criterios`` cuyo ``recomendacion_id``
        esta en la lista, o ``None`` si el cliente no devolvio el conteo exacto
        (en ese caso el resumen lo informa y no se puede confirmar el numero).

    Raises:
        Exception: cualquier error de la API se propaga al llamador, que lo
            reporta con su causa.
    """
    respuesta = (
        supabase.table(TABLA_EVALUACIONES)
        .select("id", count="exact")
        .in_("recomendacion_id", recomendacion_ids)
        .limit(1)
        .execute()
    )
    if respuesta.count is None:
        return None
    return int(respuesta.count)


def _imprimir_confirmacion_guardado(
    recomendaciones_guardadas: int,
    evaluaciones_esperadas: int,
    evaluaciones_confirmadas: int | None,
) -> bool:
    """Imprime la confirmacion de la escritura en Supabase y verifica los conteos.

    Args:
        recomendaciones_guardadas: cantidad de recomendaciones guardadas en esta
            corrida.
        evaluaciones_esperadas: 6 por recomendacion (una fila por criterio).
        evaluaciones_confirmadas: conteo leido de vuelta de
            ``evaluaciones_criterios`` para esas recomendaciones, o ``None`` si no
            se pudo leer.

    Returns:
        ``True`` si los conteos coinciden o si no se pudieron verificar;
        ``False`` si el conteo confirmado no coincide con el esperado.
    """
    print()
    print("=" * ANCHO_REPORTE)
    print("CONFIRMACION EN SUPABASE")
    print("=" * ANCHO_REPORTE)
    print(f"{'Recomendaciones guardadas':<32}: {recomendaciones_guardadas}")
    print(f"{'Evaluaciones (6 x recomendacion)':<32}: {evaluaciones_esperadas}")

    if evaluaciones_confirmadas is None:
        print(f"{'Evaluaciones confirmadas':<32}: no se pudo leer el conteo exacto.")
        print()
        print("Recomendaciones y evaluaciones guardadas en Supabase.")
        print("Verifique en Supabase con:")
        print("  select recomendacion_id, count(*) from evaluaciones_criterios")
        print("  group by recomendacion_id;")
        return True

    print(f"{'Evaluaciones confirmadas':<32}: {evaluaciones_confirmadas}")
    print()

    if evaluaciones_confirmadas != evaluaciones_esperadas:
        print("ERROR: las evaluaciones guardadas no coinciden con las esperadas.")
        print("       Revise la tabla 'evaluaciones_criterios' antes de dar el")
        print("       flujo por bueno.")
        return False

    print("Recomendaciones y evaluaciones guardadas en Supabase.")
    print(
        f"  - {recomendaciones_guardadas} filas en la tabla "
        f"'{TABLA_RECOMENDACIONES}'"
    )
    print(f"  - {evaluaciones_confirmadas} filas en la tabla '{TABLA_EVALUACIONES}'")
    print("  - cada recomendacion quedo con sus 6 criterios evaluados.")
    return True


def main() -> int:
    """Punto de entrada del demo.

    Genera las recomendaciones, imprime el reporte de detalle (encabezado,
    cantidad generada, tabla por producto y resumen agregado), pregunta si
    guardarlas (default: no) y, solo si se confirma, guarda y evalua.

    Returns:
        Codigo de salida del proceso: 0 si el flujo termino bien (incluidos los
        casos de cancelacion y de "no hay nada que guardar") y 1 si faltan
        credenciales, falla un paso o los conteos finales no cuadran.
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

    _imprimir_cabecera("FLUJO COMPLETO: RECOMENDACIONES + RUBRICA DE 6 CRITERIOS")

    # --- Estado inicial de la tabla -----------------------------------------
    try:
        existentes: int = _contar_recomendaciones_existentes(supabase)
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print("ERROR: no se pudo leer la tabla 'recomendaciones'.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1

    print()
    print(f"Recomendaciones que ya habia en la tabla: {existentes}")
    if existentes and not _confirmar_continuar(existentes):
        print("Operacion cancelada: no se escribio nada en Supabase.")
        return 0

    # --- Paso 1: generar recomendaciones ------------------------------------
    print()
    print("[1/4] Generando recomendaciones con el motor OR...")
    try:
        recomendaciones: pd.DataFrame = generar_recomendaciones(supabase)
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print("ERROR en el paso 1: fallo la generacion de recomendaciones.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1

    # --- Reporte de detalle -------------------------------------------------
    # Sale del DataFrame que devuelve el motor, asi que se imprime siempre (se
    # guarde o no) y antes de la pregunta de guardado: es lo que se mira para
    # decidir si vale la pena guardar.
    _imprimir_reporte(recomendaciones)
    _imprimir_resumen(recomendaciones)

    if recomendaciones.empty:
        print()
        print("No se guardo ni se evaluo nada. Fin.")
        return 0

    # --- Decision del usuario: guardar o no (default: no guardar) -----------
    print()
    if not _preguntar_guardar():
        print("Operacion cancelada: no se escribio nada en Supabase.")
        print(f"Las {len(recomendaciones)} recomendaciones de arriba se generaron y se")
        print("muestran en el reporte, pero no se guardaron: sin el 'recomendacion_id'")
        print("que asigna Supabase al insertar, la rubrica no se puede evaluar.")
        return 0

    # --- Paso 2: guardar las recomendaciones --------------------------------
    print()
    print(f"[2/4] Guardando las recomendaciones en '{TABLA_RECOMENDACIONES}'...")
    try:
        guardadas: pd.DataFrame = guardar_recomendaciones(supabase, recomendaciones)
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print("ERROR en el paso 2: fallo el guardado de las recomendaciones.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1

    print(f"      Recomendaciones guardadas (con UUID): {len(guardadas)}")

    # --- Paso 3: cruzar los UUID con las recomendaciones --------------------
    print()
    print("[3/4] Cruzando los UUID con las recomendaciones (merge por producto_id)...")
    try:
        con_id: pd.DataFrame = _recomendaciones_con_id(recomendaciones, guardadas)
    except ValueError as error:
        print("ERROR en el paso 3: no se pudo armar la entrada del evaluador.")
        print(f"       Causa: {error}")
        return 1

    print(f"      Recomendaciones listas para evaluar: {len(con_id)}")

    # --- Paso 4: evaluar la rubrica y guardar -------------------------------
    print()
    print("[4/4] Aplicando la rubrica de 6 criterios y guardando las evaluaciones...")
    try:
        evaluar_y_guardar(supabase, con_id)
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print("ERROR en el paso 4: fallo la evaluacion o el guardado de las")
        print("       evaluaciones. Si el INSERT fallo a medias, revise la tabla.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1

    # --- Verificacion y confirmacion de la escritura ------------------------
    esperadas: int = EVALUACIONES_POR_RECOMENDACION * len(con_id)
    try:
        confirmadas: int | None = _contar_evaluaciones(
            supabase, list(con_id["recomendacion_id"])
        )
    except Exception as error:  # noqa: BLE001 - se reporta y se sale con codigo 1
        print()
        print("ERROR: las evaluaciones se guardaron, pero no se pudo leer el conteo")
        print("       de vuelta para confirmarlo.")
        print(f"       Causa: {type(error).__name__}: {error}")
        return 1

    return (
        0
        if _imprimir_confirmacion_guardado(len(con_id), esperadas, confirmadas)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

