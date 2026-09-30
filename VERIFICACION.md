# Verificación del sistema

Este documento es la **lista de comprobación ejecutable** del MVP: dice, paso a
paso, qué comando correr y qué resultado mirar para confirmar que el sistema
funciona. Está dirigido a quien retoma el repositorio (desarrollador nuevo, QA,
docente o el propio autor meses después) y asume solo que el setup ya está hecho.

Los niveles están ordenados de menor a mayor costo y de menor a mayor
dependencia externa: el 1 no toca red, el 2 valida las credenciales, el 3 corre
el pipeline completo contra el seed, el 4 prueba la configurabilidad (RF-11) y
el 5 deja la base en un estado conocido. Se pueden correr todos en orden, o solo
los niveles que hagan falta según lo que se cambió.

Para el **setup detallado** (clonado, `.env`, orden de aplicación del SQL,
instalación de dependencias), ver `README.md` §§2 a 6. Este documento no repite
ese procedimiento: lo da por hecho y solo verifica que funcione. Las decisiones
de diseño que explican los valores esperados se referencian en cada nivel y
están en `DECISIONES_DISENO.md`.

Cifras y salidas de este documento verificadas sobre el commit `23b134b`
(rama `master`), el 30 de septiembre de 2026.

---

## Prerrequisitos

- Python 3.11 o superior instalado y disponible en el `PATH`.

  ```bash
  python --version
  ```

- Dependencias de Python instaladas:

  ```bash
  cd backend
  pip install -r requirements.txt
  ```

  `requirements.txt` instala `supabase`, `python-dotenv`, `openai`, `pandas`,
  `numpy` y `pytest`.

- Archivo `.env` en la **raíz** del proyecto, con las claves de Supabase y del
  LLM (ver `README.md` §2). Se copia de `.env.example`. Las claves que se usan
  en la verificación son: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
  `SUPABASE_SERVICE_ROLE_KEY`, `LLM_BASE_URL`, `LLM_API_KEY` y `LLM_MODEL`.

- Base de datos cargada en Supabase: `db/schema.sql` (7 tablas, RLS y los 10
  parámetros) y luego `db/seed_sintetico.sql` (6 productos, 4 proveedores, 8
  relaciones producto-proveedor y 72 registros de demanda), aplicados en ese
  orden desde el SQL Editor (ver `README.md` §3).

- Estar en la **raíz del proyecto** para todos los comandos, salvo donde se
  indique otro directorio (el Nivel 1 pide `cd backend`). Los scripts de
  `scripts/` resuelven sus rutas a partir de `__file__`, así que funcionan
  desde cualquier directorio, pero las rutas de este documento asumen la raíz.

- Acceso a internet: los niveles 2, 3, 4 y 5 hablan con el Supabase real (y el
  nivel 2, con el proveedor del LLM).

---

## Nivel 1: Tests unitarios

Verifica la lógica pura del sistema sin tocar red ni base de datos: los tests
inyectan DataFrames sintéticos y (para la configurabilidad) un cliente falso de
Supabase. Es el nivel más rápido (unos 4 o 5 segundos los 403 tests) y el que
conviene correr después de cualquier cambio antes de gastar una corrida contra
Supabase.

### Comando

```bash
cd backend
python -m pytest -q
```

Notas sobre el directorio:

- `python -m pytest -q` también funciona desde la raíz del proyecto (pytest
  agrega `backend/` al `sys.path` al recolectar los tests, por eso el import
  `from src.config import ...` resuelve). Se documenta con `cd backend` porque
  es la forma que fija `README.md` §6.
- Lo que **no** funciona es ejecutar un archivo de test directamente
  (`python tests/test_abc.py`): falla con
  `ModuleNotFoundError: No module named 'src'` porque el directorio del archivo
  (`backend/tests/`) queda en `sys.path[0]` y `src` no es importable desde ahí.

### Resultado esperado

La última línea debe ser del tipo:

```text
403 passed in 4.15s
```

Concretamente: **403 tests pasando, 0 fallos, 0 skips**. Si aparece cualquier
`failed`, `error` o `skipped`, el nivel no está aprobado.

### Qué verifica

- La lógica de los 6 módulos del motor OR (`backend/src/motor/`): ABC, XYZ,
  estimación de demanda, EOQ/ROP, score de proveedor y oportunidad de ahorro.
  254 de los 403 tests son de estos módulos.
- El recomendador (`backend/src/recomendador.py`), con DataFrames sintéticos:
  orquestación de los módulos, elección de proveedor y fronteras de urgencia.
- El evaluador (`backend/src/evaluador.py`), con DataFrames sintéticos: la
  rúbrica de 6 criterios. Son 76 tests.
- El módulo de configurabilidad (`backend/src/config.py`) con un cliente falso
  de Supabase: que `cargar_parametros` exija las 10 claves, que lance
  `ValueError` si falta alguna (incluida la tabla vacía) y que importar el
  módulo no arrastre el paquete `supabase`.
- Que no hay regresiones: la suite incluye tests guardianes que impiden que las
  constantes ya migradas vuelvan a los módulos y que las comparaciones de
  frontera se hagan con tolerancia (1e-9), no con igualdad exacta de punto
  flotante (ver `DECISIONES_DISENO.md`, D-07).

---

## Nivel 2: Verificación de entorno

Valida que las credenciales del `.env` sirven para lo que tienen que servir:
que el aislamiento de seguridad (RLS) está aplicado en Supabase y que el LLM
responde. Cada script es independiente y avisa con un mensaje de error propio si
le falta su variable. Los tres hacen `load_dotenv` de `.env` en la raíz
(derivada de `__file__`), así que se pueden correr desde cualquier directorio.

Este nivel requiere `.env` con claves válidas. Los dos primeros requieren
además acceso al proyecto real de Supabase; el tercero, conexión con el
proveedor del LLM y no toca Supabase.

### Comando

```bash
python scripts/verificar_rls.py
python scripts/verificar_service_role.py
python scripts/verificar_zai.py
```

### Resultado esperado

Los tres scripts terminan sin errores (código de salida 0) y sin ninguna línea
que contenga `FALLO`. (Las salidas reales llevan emojis; aquí se transcriben
sin ellos.)

- `verificar_rls.py`: intenta un `INSERT` en `productos` con la `anon key` y
  confirma que la base lo rechaza por RLS. La línea esperada dice
  `CORRECTO: RLS bloqueó el INSERT con anon key`, seguida del error devuelto por
  Supabase (referencia a `row-level security` o código `42501`). Si en cambio
  imprime `FALLO DE SEGURIDAD`, RLS no está bloqueando y **no** se debe seguir:
  revisar las políticas de `db/schema.sql`.
- `verificar_service_role.py`: recorre el ciclo completo de escritura con la
  `service_role key` (INSERT, SELECT, UPDATE, DELETE de la misma fila en
  `productos`) y cierra con `Aislamiento verificado`. Debe mostrar las cuatro
  operaciones en OK. La fila de prueba queda borrada al final; si el DELETE
  falla, el script avisa y hay que limpiarla a mano (nombre
  `test_service_role`, categoría `prueba_rls_actualizada`).
- `verificar_zai.py`: envía un mensaje mínimo al modelo configurado en
  `LLM_MODEL` y muestra su respuesta. Con una conexión sana se ve:

  ```text
  Respuesta del modelo: ok
  ```

### Qué verifica

- Que la seguridad del proyecto (RLS) está correctamente configurada: `anon`
  solo lectura, `service_role` con escritura completa. Es la convención
  documentada en `DECISIONES_DISENO.md` (decisiones transversales: "Escritura
  solo con `service_role`") y la que habilita que el frontend y el agente usen
  la `anon key` sin poder escribir.
- Que el LLM (Z.ai / GLM) es accesible con las claves y el `base_url` del
  `.env`, y que el `LLM_MODEL` configurado existe.
- Que las claves del `.env` son válidas y están bien escritas: un error de
  tipeo en el nombre de la variable, una clave truncada o un `.env` en el
  directorio equivocado hacen fallar este nivel y no el Nivel 1 (que no toca
  red).

---

## Nivel 3: Flujo end-to-end (recomendador + evaluador)

Corre el pipeline completo contra los datos reales del seed: lee las cuatro
tablas de datos más `parametros_configuracion`, genera las recomendaciones con
el motor OR, y si se confirma el guardado, persiste las recomendaciones en
`recomendaciones` y aplica la rúbrica de 6 criterios guardando el resultado en
`evaluaciones_criterios`. Tarda unos segundos.

Requiere `.env` con la `SUPABASE_SERVICE_ROLE_KEY` (el guardado escribe en
tablas con RLS de solo lectura, así que la `anon key` no alcanza) y el seed
cargado. **No escribe nada si no se confirma**: el default de la pregunta final
es no guardar.

### Comando

```bash
python scripts/demo_flujo_completo.py
```

Interacción del script (dos preguntas, ambas con default "no"):

1. Si la tabla `recomendaciones` ya tiene filas, primero avisa y pregunta
   `Desea continuar de todas formas? [S/N]` (Enter = cancelar). Es una guarda
   para no acumular corridas sobre un histórico ya cargado.
2. Al final del reporte pregunta
   `Desea guardar las recomendaciones en Supabase? [S/N]`. El script muestra
   `[S/N]` y el default es **N**: presionar Enter no guarda nada. Solo una
   respuesta afirmativa explícita (`s`, `si`, `y`, `yes`) continúa con los pasos
   de guardado y evaluación.

Si no hay consola interactiva (por ejemplo, `stdin` cerrado o una corrida desde
CI), ambas preguntas se resuelven como "no" y el script no escribe nada.

### Resultado esperado

Con Enter (no guardar):

- Sección `REPORTE DE RECOMENDACIONES DE COMPRA` con
  `Recomendaciones generadas: 6`.
- Tabla de detalle por producto con las columnas: `producto`, `proveedor`,
  `clase_abc`, `clase_xyz`, `urgencia`, `stock_actual`, `punto_reorden`,
  `cantidad_recomendada`, `ahorro_neto_estimado` y `score_proveedor`.
- Sección `RESUMEN` con los conteos por urgencia (`Crítico`, `Atención`,
  `Sin riesgo`), la línea `Recomendaciones con 'Ahorro detectado': N` y
  `Suma de ahorro_neto_estimado: $N`.
- Cierre `Operacion cancelada: no se escribio nada en Supabase`, código de
  salida 0.

Con `s` (guardar), además de lo anterior:

- Pasos `[2/4]` guardado (6 recomendaciones con UUID), `[3/4]` cruce de los UUID
  con las recomendaciones del motor (el cruce es 1:1 por `producto_id`),
  `[4/4]` rúbrica de 6 criterios y guardado.
- 36 evaluaciones guardadas: 6 recomendaciones × 6 criterios.
- Confirmación leída de vuelta de la base con el conteo de evaluaciones.

**Estado actual con el seed** (valores esperados con los parámetros por defecto):

- Atención: 1 (`SEED_Engrane G7`)
- Sin riesgo: 5
- Crítico: 0 (esperado con los `stock_actual` del seed; está registrado en
  `PENDIENTES.md` como ajuste opcional)
- Con "Ahorro detectado": 2 (`SEED_Engrane G7`, `SEED_Tornillo M3`)
- Suma de ahorro neto: aproximadamente $1,869.75

Tabla de referencia del reporte (mismo orden que imprime el script, por
urgencia):

| producto | proveedor | clase_abc | clase_xyz | urgencia | stock_actual | punto_reorden | cantidad_recomendada | ahorro_neto_estimado | score_proveedor |
|---|---|---|---|---|---|---|---|---|---|
| SEED_Engrane G7 | SEED_ProvCo | A | Y | Atención | 15.00 | 21.60 | 200.00 | 1,470.64 | 96.20 |
| SEED_Tornillo M3 | SEED_CheapSupply | B | X | Sin riesgo | 950.00 | 816.67 | 5,000.00 | 278.58 | 76.00 |
| SEED_Widget B | SEED_FastParts | A | X | Sin riesgo | 120.00 | 20.83 | 300.00 | 120.53 | 86.00 |
| SEED_Cable HDMI | SEED_FastParts | C | Y | Sin riesgo | 400.00 | 53.60 | 339.77 | 0.00 | 86.00 |
| SEED_Pintura 1L | SEED_ProvCo | A | X | Sin riesgo | 260.00 | 85.07 | 343.73 | 0.00 | 96.20 |
| SEED_Widget A | SEED_ProvCo | A | X | Sin riesgo | 30.00 | 28.70 | 156.84 | 0.00 | 96.20 |

Las diferencias con las clases ABC/XYZ que se comentan en el propio seed están
documentadas como deuda técnica (el seed se diseñó a ojo; el motor calcula los
CV reales): ver `PENDIENTES.md`, sección de deuda técnica.

### Qué verifica

- Que el motor produce recomendaciones con datos reales (no sintéticos) leídos
  de Supabase, con proveedor elegido, cantidades y ahorro cuantificado.
- Que el recomendador orquesta correctamente los 6 módulos: cada recomendación
  es la salida encadenada de ABC, XYZ, demanda, EOQ/ROP, proveedor y ahorro.
- Que el evaluador aplica la rúbrica de 6 criterios sobre esas recomendaciones
  (36 evaluaciones por corrida completa, sin faltantes ni duplicados).
- Que la integración con Supabase funciona de punta a punta: lectura de las
  cinco tablas, normalización de nombres de columna, escritura en
  `recomendaciones`, cruce de los UUID generados y escritura en
  `evaluaciones_criterios`.

---

## Nivel 4: Verificación de configurabilidad (RF-11)

Verifica que los parámetros de configuración afectan los resultados del motor
sin necesidad de tocar código: se cambia un valor en
`parametros_configuracion`, se vuelve a correr el motor y se compara con la
corrida anterior.

Requiere acceso al **SQL Editor de Supabase** (para los `UPDATE`) además de
`.env` y del seed. No requiere reiniciar nada: el script lee la tabla en cada
corrida. El alcance de lo configurable (los 10 umbrales de la tabla y por qué
el resto de las constantes quedó en código) está en `DECISIONES_DISENO.md`,
D-03; la convención de unidades de cada parámetro, en D-04.

**Este nivel ya se ejecutó con éxito** (Prueba 1 y Prueba 2, con restauración
de los 10 parámetros) y el resultado está registrado en `PENDIENTES.md`
("Verificación end-to-end de configurabilidad (RF-11)") y en
`ESTADO_IMPLEMENTACION.md` (sección de configurabilidad y métricas). Lo que
sigue es el procedimiento para reproducirlo.

Antes de empezar, dejar constancia de los valores de partida para poder
restaurarlos:

```sql
SELECT nombre_parametro, valor
FROM parametros_configuracion
ORDER BY nombre_parametro;
```

### Prueba 1: Cambiar abc_clase_a_pct

1. En el SQL Editor de Supabase:

   ```sql
   UPDATE parametros_configuracion
   SET valor = 50
   WHERE nombre_parametro = 'abc_clase_a_pct';
   ```

2. Correr el script de demo (responder Enter en la pregunta de guardado para no
   escribir en la base):

   ```bash
   python scripts/demo_flujo_completo.py
   ```

3. Comparar con el estado original (`abc_clase_a_pct = 80`):
   - Con 50, algunos productos cambian de clase A a B. En el estado actual del
     seed cambian 3: `SEED_Widget B`, `SEED_Pintura 1L` y `SEED_Widget A`.
   - El resto del reporte (proveedor, urgencias, cantidades) no cambia: el
     umbral ABC solo mueve la clasificación, no la decisión de compra.

4. Restaurar el valor original:

   ```sql
   UPDATE parametros_configuracion
   SET valor = 80
   WHERE nombre_parametro = 'abc_clase_a_pct';
   ```

### Prueba 2: Cambiar ahorro_neto_min_pct

1. En el SQL Editor de Supabase:

   ```sql
   UPDATE parametros_configuracion
   SET valor = 10
   WHERE nombre_parametro = 'ahorro_neto_min_pct';
   ```

2. Correr el script de demo:

   ```bash
   python scripts/demo_flujo_completo.py
   ```

3. Comparar con el estado original (`ahorro_neto_min_pct = 3`):
   - Con 10, la cantidad de productos con "Ahorro detectado" baja de 2 a 0,
     porque el umbral es más estricto.
   - Las filas de la tabla de detalle siguen mostrando el mismo
     `ahorro_neto_estimado`; lo que cambia es la clasificación del estado de
     ahorro (criterio 6).

4. Restaurar el valor original:

   ```sql
   UPDATE parametros_configuracion
   SET valor = 3
   WHERE nombre_parametro = 'ahorro_neto_min_pct';
   ```

El umbral de ahorro es un **porcentaje del costo total del pedido**, no un
monto absoluto, así que 3 significa 3 %: la comparación es
`ahorro_neto >= (costo_total_pedido × 3 / 100)`. El criterio y su fórmula están
en `DECISIONES_DISENO.md` D-01 (lectura B del criterio 6) y D-02 (notación
efectiva del umbral); las comparaciones de frontera usan una tolerancia de 1e-9
para no depender del ruido de punto flotante (D-07).

### Qué verifica

- Que los 10 parámetros de `parametros_configuracion` se leen correctamente
  (si faltara alguno, `cargar_parametros` lanzaría `ValueError` y el script
  fallaría en el paso 1, no en silencio).
- Que el recomendador los propaga al motor como argumentos, sin lecturas
  adicionales de la tabla (ver D-04 y las notas de configurabilidad de
  `PENDIENTES.md`).
- Que el motor los usa en los cálculos y que el evaluador los usa en la
  rúbrica.
- Que un cambio de configuración afecta los resultados sin recompilar ni
  reiniciar (RF-11 y criterio de aceptación 7 de `MVP.md`).

Advertencia: `config.py` no valida rangos ni unidades. Un valor escrito en la
unidad equivocada (por ejemplo `3` donde se espera `0.03`) cambia
clasificaciones en silencio, sin lanzar error (ver D-04, consecuencias).

---

## Nivel 5: Verificación de la base de datos

Cierra la verificación mirando el estado de la base después de las pruebas
anteriores. No hay script para este nivel: se consulta con el SQL Editor de
Supabase.

### Comandos SQL en el Editor de Supabase

```sql
SELECT COUNT(*) FROM recomendaciones;
SELECT COUNT(*) FROM evaluaciones_criterios;
SELECT nombre_parametro, valor FROM parametros_configuracion ORDER BY nombre_parametro;
```

### Resultado esperado

- `recomendaciones`: 0 filas si en el Nivel 3 no se guardó (o si nunca se corrió
  con `s`), o N filas si se guardó (6 por corrida de demo, acumulando entre
  corridas).
- `evaluaciones_criterios`: 0 filas si no se guardó, o 6N filas si se guardó
  (6 criterios por recomendación: 36 con una corrida).
- `parametros_configuracion`: 10 filas con sus valores originales:

  | Parámetro | Valor original |
  |---|---|
  | `abc_clase_a_pct` | 80 |
  | `abc_clase_b_pct` | 95 |
  | `ahorro_neto_min_pct` | 3 |
  | `cv_confianza_alta` | 0.5 |
  | `cv_confianza_media` | 1 |
  | `demanda_ventana_default` | 6 |
  | `eoq_max_pct` | 110 |
  | `eoq_min_pct` | 90 |
  | `score_proveedor_confiable` | 80 |
  | `score_proveedor_riesgoso` | 60 |

  Si el listado trae menos de 10 filas, o valores distintos de estos, quedó
  alguna prueba del Nivel 4 sin restaurar.

Para volver a un estado limpio de las tablas de escritura (opcional, solo si se
quiere repetir la demo desde cero):

```sql
DELETE FROM evaluaciones_criterios;
DELETE FROM recomendaciones;
```

Ese `DELETE` requiere la `service_role key` (o el rol propietario), no la
`anon key`.

### Qué verifica

- Que la base quedó en el estado esperado después de las pruebas: las tablas de
  escritura con las filas correspondientes a lo que se confirmó guardar y nada
  más.
- Que los parámetros están restaurados tras las pruebas de configurabilidad.
- Que el contenido de `evaluaciones_criterios` es consistente con el de
  `recomendaciones` (6 filas por recomendación).

---

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'src'"

Significa que se está ejecutando código que importa el paquete `src` desde un
directorio donde `backend/` no está en el `sys.path`:

- Si pasa con los tests, es porque se ejecutó el archivo directamente
  (`python tests/test_abc.py`). Correr la suite siempre con `python -m pytest`
  desde `backend/` (o desde la raíz, que también funciona).
- Si pasa con un `python -c "from src... import ..."` o con un script propio
  escrito a mano, agregar `backend/` al path antes del import, o correr desde
  `backend/`. Los scripts de `scripts/` ya lo hacen solos (agregan `backend/`,
  el padre de `src`, no `backend/src`), así que no hace falta tocar nada para
  correr los niveles 2 y 3.
- Los tres `verificar_*.py` no importan `src`: no pueden fallar por este motivo.

### Error: "Supabase connection failed" (o timeout en el Nivel 2/3)

- Revisar que el `.env` esté **en la raíz** del proyecto (los scripts lo leen de
  `Path(__file__).parent.parent / ".env"`), no en `backend/` ni en `scripts/`.
- Verificar los nombres exactos de las variables contra `.env.example`:
  `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`. Sin
  `https://` en la URL, o con la clave de otro proyecto, falla.
- El proyecto de Supabase tiene que estar activo (un proyecto pausado responde
  con error de red).
- Si falla solo `verificar_zai.py`, el problema es del LLM, no de Supabase:
  revisar `LLM_BASE_URL`, `LLM_API_KEY` y que `LLM_MODEL` exista en Z.ai.

### Error: "Falta algún parámetro en parametros_configuracion"

El mensaje real es de `src.config.cargar_parametros` (el Nivel 3 falla en el
paso 1 con él):

```text
verificar_parametros: faltan N de los 10 parámetros de configuración de 'parametros_configuracion': <lista>.
```

- Si la tabla está vacía o incompleta: aplicar `db/schema.sql` (crea la tabla y
  hace el `INSERT` de los 10 parámetros) o añadir a mano las filas que faltan
  respetando los valores originales del Nivel 5.
- Si es un test del Nivel 1 que falla por este mensaje, no es la base real: los
  tests usan un cliente falso y el caso está cubierto a propósito (que la tabla
  vacía lance `ValueError`). Un cambio en `PARAMETROS_DEFAULT` puede romper esas
  expectativas: revisar `backend/tests/test_config.py`.

### Los tests fallan

- Correr siempre con `python -m pytest -q` (el import `src` depende de que
  pytest agregue `backend/` al path). Ver la primera entrada de esta sección.
- Si se cambió la firma de un módulo o se agregó un parámetro, la expectativa de
  un test puede estar desactualizada a propósito: correr sin `-q` (o con `-vv`)
  para ver qué test falla y su traceback, y ubicarlo en `backend/tests/`.
- Para aislar un módulo:

  ```bash
  cd backend
  python -m pytest tests/test_ahorro.py -vv
  ```

- Un fallo de frontera por un decimal (un `0.03` que no se compara exacto) es
  el caso que cubren las tolerancias de 1e-9 (D-07); si aparece, revisar el
  valor comparado, no la tolerancia.

### La demo no genera 6 recomendaciones

- El reporte dice `No hay recomendaciones: ningun producto cumple los criterios
  minimos`. Revisar que el seed esté cargado y completo: cada producto necesita
  al menos 2 periodos de historial, un proveedor asociado y un CV calculable.
  Los datos entran aplicando `db/seed_sintetico.sql` (ver `README.md` §3).
- Si el conteo es distinto de 6 pero no es 0, comparar `stock_actual`,
  `punto_reorden` y las clases ABC/XYZ contra la tabla de referencia del
  Nivel 3, y confirmar que los 10 parámetros están en sus valores originales
  (Nivel 5).

### Los acentos del reporte se ven mal en la consola

Es un problema cosmético de la página de códigos de la consola de Windows, no
de los datos. En PowerShell se puede correr `chcp 65001` antes de la demo (o
`$env:PYTHONIOENCODING = "utf-8"`); los valores numéricos y las clases no
cambian.

---

## Resumen de verificación

| Nivel | Requisitos | Comando | Resultado |
|---|---|---|---|
| 1. Tests | Instalado | `python -m pytest -q` (desde `backend/`) | 403 pasando |
| 2. Entorno | `.env`, Supabase, LLM | `python scripts/verificar_rls.py`, `verificar_service_role.py`, `verificar_zai.py` | 3 scripts OK |
| 3. End-to-end | Seed cargado, `.env` | `python scripts/demo_flujo_completo.py` | 6 recomendaciones, 36 evaluaciones |
| 4. Configurabilidad | SQL Editor, `.env`, seed | `UPDATE` + demo (Pruebas 1 y 2) | Cambios coherentes y restaurados |
| 5. Estado de la BD | SQL Editor | `SELECT COUNT(*)` / `SELECT nombre_parametro, valor` | Valores esperados |

**Estado al escribir este documento** (commit `23b134b`): los niveles 1 y 3 se
corrieron en vivo, con el resultado de la tabla de referencia del Nivel 3
(403 pasando, 6 recomendaciones, Atención 1, Sin riesgo 5, Crítico 0, 2 con
"Ahorro detectado", suma $1,869.75) y sin escribir nada en Supabase
(`recomendaciones` seguía en 0 filas). Los niveles 2, 4 y 5 quedan como
procedimiento reproducible; su última corrida exitosa está registrada en
`PENDIENTES.md` ("Notas de integración") y `ESTADO_IMPLEMENTACION.md`
(verificación end-to-end de configurabilidad y métricas).

Si los cinco niveles pasan, el sistema está verificado en su estado actual. Lo
que falta construir (agente conversacional, frontend y script de ingesta) no
tiene verificación todavía: su estado está en `ESTADO_IMPLEMENTACION.md` y la
deuda técnica abierta en `PENDIENTES.md`.
