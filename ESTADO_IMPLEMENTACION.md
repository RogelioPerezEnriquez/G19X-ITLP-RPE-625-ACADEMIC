# Estado de implementación

**Fecha del documento:** 30 de septiembre de 2026
**Commit de referencia:** `8fb1d7a` (rama `master`)
**Proyecto:** Sistema Inteligente de Optimización de Compras

Este documento es una **foto del estado actual** de la implementación: qué
componentes del MVP están construidos y verificados, cuáles no, y con qué
evidencia se sostiene cada afirmación. No es una especificación ni una hoja de
ruta. La definición del producto está en `MVP.md` (requisitos, alcance,
rúbrica y modelo de datos) y la deuda técnica abierta en `PENDIENTES.md`; cuando
hace falta ese nivel de detalle, este documento referencia esos archivos en
lugar de repetir su contenido.

Las cifras, comandos y salidas que aparecen aquí se verificaron sobre el commit
indicado.

---

## Resumen ejecutivo

El MVP tiene implementada y verificada toda la capa de cálculo y de
persistencia: esquema de base de datos en Supabase (7 tablas, RLS y 10
parámetros configurables), seed sintético de prueba, motor de investigación de
operaciones completo (6 módulos puros: ABC, XYZ, demanda, EOQ/ROP, proveedor y
ahorro), recomendador que orquesta ese motor y evaluador que aplica la rúbrica
de 6 criterios, con 403 tests pasando y una corrida end-to-end exitosa contra
los datos reales del seed. Falta la capa de interacción: el script de ingesta
CSV/Excel (RF-01), el agente conversacional (RF-09, RF-10) y el frontend Vue 3
(RF-07, RF-08, RF-12). En consecuencia, el sistema hoy se opera desde scripts y
terminal, y los criterios de aceptación del MVP ligados a la interfaz y al
agente (puntos 1, 4, 5, 6 y 8 de `MVP.md` §15) todavía no se pueden cumplir.

---

## Estado por componente del MVP

Referencia de requisitos: `MVP.md` §5.1 (alcance incluido) y §6 (requisitos
funcionales).

| Componente | Estado | Notas |
|---|---|---|
| Esquema de base de datos | ✅ Completo | `db/schema.sql` (versión 2): 7 tablas, claves foráneas, restricciones `check` de dominio, índices de apoyo, RLS habilitado en las 7 tablas e inserción de los 10 parámetros de configuración. |
| Datos sintéticos | ✅ Completo | `db/seed_sintetico.sql`: 6 productos, 4 proveedores, 8 relaciones producto-proveedor y 72 registros de demanda (12 periodos por producto). |
| Verificación de seguridad (RLS) | ✅ Completo | `scripts/verificar_rls.py` y `scripts/verificar_service_role.py`: `anon` solo lectura, `service_role` con escritura. Todo el backend escribe con `service_role`. |
| Conexión con LLM | ✅ Completo | `scripts/verificar_zai.py` valida la configuración y la conectividad con el proveedor (Z.ai / GLM) a partir de las variables de `.env`. Es verificación de conectividad: todavía no existe agente que consuma la API. |
| Motor OR | ✅ Completo | 6 módulos puros en `backend/src/motor/` (RF-02, RF-03, RF-04) con 254 de los 403 tests. Ningún módulo accede a red, base de datos ni archivos. |
| Recomendador | ✅ Completo | `backend/src/recomendador.py` orquesta el motor (RF-05) y persiste en `recomendaciones`. Verificado contra el seed: 6 recomendaciones generadas. |
| Evaluador (rúbrica de 6 criterios) | ✅ Completo | `backend/src/evaluador.py` (RF-06), 76 tests. Escribe en `evaluaciones_criterios`: 6 recomendaciones × 6 criterios = 36 evaluaciones por corrida completa. |
| Configurabilidad | ✅ Completo | Los 10 parámetros de `parametros_configuracion` llegan a los módulos del motor como argumentos (RF-11), y se verificó end-to-end que cambiarlos altera los resultados. Otras constantes (pesos del score, periodos por año, margen de seguridad, `MIN_PERIODOS`, etiquetas de urgencia) siguen en código por decisión de alcance: ver `PENDIENTES.md`. |
| Agente conversacional | ⏳ Pendiente | RF-09 y RF-10. El paquete `backend/src/agente/` existe, pero solo contiene un `__init__.py` vacío. |
| Frontend | ⏳ Pendiente | RF-07, RF-08 y RF-12. El directorio `frontend/` todavía no existe en el repositorio. |
| Script de ingesta | ⏳ Pendiente | RF-01. El paquete `backend/src/ingesta/` existe, pero solo contiene un `__init__.py` vacío. Hoy los datos entran aplicando `db/seed_sintetico.sql` a mano en el SQL Editor de Supabase. |

---

## Métricas del proyecto

- Módulos del motor: 6
- Archivos de test: 9 (todos en `backend/tests/`)
- Tests pasando: 403 (0 fallos, ~5,5 s)
- Parámetros configurables: 10 (tabla `parametros_configuracion`)
- Tablas en la base de datos: 7
- Scripts de demo/verificación: 5 (`scripts/`)
- Módulos de producción con entrada/salida: 3 (`config.py`, `recomendador.py`, `evaluador.py`)
- Paquetes placeholder vacíos: 2 (`backend/src/agente/`, `backend/src/ingesta/`)
- Filas del seed: 6 productos, 4 proveedores, 8 relaciones producto-proveedor, 72 registros de demanda
- Recomendaciones generadas contra el seed: 6
- Evaluaciones por corrida completa (6 recomendaciones × 6 criterios): 36

Distribución de tests por archivo:

| Archivo | Tests |
|---|---|
| `backend/tests/test_abc.py` | 35 |
| `backend/tests/test_ahorro.py` | 57 |
| `backend/tests/test_config.py` | 36 |
| `backend/tests/test_demanda.py` | 36 |
| `backend/tests/test_eoq_rop.py` | 30 |
| `backend/tests/test_evaluador.py` | 76 |
| `backend/tests/test_proveedor.py` | 45 |
| `backend/tests/test_recomendador.py` | 37 |
| `backend/tests/test_xyz.py` | 51 |
| **Total** | **403** |

Resultado observado de la corrida del flujo completo contra el seed (commit de
referencia):

| Métrica del reporte | Valor |
|---|---|
| Recomendaciones generadas | 6 |
| Urgencia "Crítico" | 0 |
| Urgencia "Atención" | 1 |
| Urgencia "Sin riesgo" | 5 |
| Recomendaciones con "Ahorro detectado" | 2 |
| Suma de `ahorro_neto_estimado` | 1.869,75 |

Que ninguna recomendación caiga en "Crítico" y que las clases ABC/XYZ calculadas
por el motor no coincidan exactamente con las diseñadas en el seed son
resultados conocidos y explicados en `PENDIENTES.md`.

---

## Implementación detallada

### Motor OR (6 módulos puros)

Los seis módulos viven en `backend/src/motor/`. Cada uno expone **una sola
función pública** que recibe y devuelve DataFrames: no accede a red, base de
datos ni sistema de archivos, no imprime ni registra nada, no modifica la
entrada y ordena la salida de forma determinista.

| Módulo | Función pública | Entradas (columnas del DataFrame) | Salidas | Parámetros configurables que consume |
|---|---|---|---|---|
| `abc.py` | `clasificar_abc(productos, umbral_clase_a, umbral_clase_b)` | `producto_id`, `costo_unitario`, `demanda_total` | El mismo DataFrame más la columna `clase_abc` (A/B/C) | `abc_clase_a_pct`, `abc_clase_b_pct` |
| `xyz.py` | `clasificar_xyz(historial, umbral_x, umbral_y)` | `producto_id`, `cantidad_demandada` | Una fila por producto con `cv` y `clase_xyz` (X/Y/Z; `None` si el CV no es calculable) | `cv_confianza_alta`, `cv_confianza_media` |
| `demanda.py` | `estimar_demanda(historial, ventana)` | `producto_id`, `periodo`, `cantidad_demandada` | Una fila por producto con `demanda_estimada` (promedio móvil) | `demanda_ventana_default` |
| `eoq_rop.py` | `calcular_eoq_rop(datos, periodos_por_año, dias_por_periodo, margen_seguridad_pct)` | `producto_id`, `costo_unitario`, `costo_ordenar`, `costo_mantener_pct_anual`, `demanda_estimada`, `lead_time_dias` | Una fila por producto con `cantidad_eoq`, `stock_seguridad` y `punto_reorden` | Ninguno: sus tres parámetros siguen hardcodeados (ver `PENDIENTES.md`) |
| `proveedor.py` | `calcular_score_proveedor(proveedores, umbral_confiable, umbral_riesgoso)` | `proveedor_id`, `cumplimiento_entrega_pct`, `tasa_defectos_pct` | Una fila por proveedor con `score` (0-100) y `estado` | `score_proveedor_confiable`, `score_proveedor_riesgoso` |
| `ahorro.py` | `calcular_ahorro(datos, umbral_ahorro_pct, periodos_por_año)` | `producto_id`, `precio_unitario`, `cantidad_umbral_descuento`, `descuento_pct`, `cantidad_eoq`, `costo_unitario`, `costo_mantener_pct_anual` | Una fila por producto con `cantidad_pedido`, `ahorro_bruto`, `costo_extra_mantener`, `ahorro_neto` y `estado` | `ahorro_neto_min_pct` |

Detalle por módulo:

- **`abc.py`** clasifica por valor económico acumulado (`costo_unitario ×
  demanda_total`), ordenado de mayor a menor: clase A hasta `abc_clase_a_pct`,
  clase B hasta `abc_clase_b_pct`, clase C por encima. Los empates de valor se
  resuelven por `producto_id` ascendente para que el acumulado sea determinista.
- **`xyz.py`** calcula el coeficiente de variación con desviación estándar
  muestral (`ddof=1`): X con CV bajo, Y con CV moderado, Z con CV alto. El CV se
  calcula una sola vez por producto y se reutiliza para la rúbrica (criterio 3).
  Los productos con menos de 2 periodos se excluyen y los de media 0 se devuelven
  con `cv` y `clase_xyz` nulos.
- **`demanda.py`** estima por promedio móvil de los `ventana` periodos más
  recientes; un producto con menos periodos que la ventana se promedia con todo
  lo que tenga. La salida queda en unidades por periodo (no anualiza).
- **`eoq_rop.py`** calcula `EOQ = sqrt(2·D·S/H)`, `SS = demanda_diaria ×
  lead_time × margen_seguridad_pct` y `ROP = demanda_diaria × lead_time + SS`.
  Si `H` es 0 (costo unitario o costo de mantener en 0) lanza `ValueError`.
- **`proveedor.py`** calcula `score = cumplimiento_entrega_pct × 0.6 +
  (100 − tasa_defectos_pct) × 0.4` y lo clasifica en Confiable, Aceptable con
  reservas o Riesgoso.
- **`ahorro.py`** evalúa el descuento por volumen: si el EOQ alcanza el umbral de
  descuento mantiene el EOQ; si no lo alcanza sube el pedido al umbral y paga el
  costo de mantener el exceso prorrateado a un periodo. Nunca reduce el pedido
  por debajo del EOQ y clasifica el resultado en "Ahorro detectado" o "Sin
  oportunidad adicional". No devuelve `costo_total_pedido`: esa columna la agrega
  el recomendador.

Todos los módulos validan de forma estricta las columnas requeridas (lanzan
`ValueError` si falta alguna, incluso con el DataFrame vacío) y comparan sus
cortes con una tolerancia de punto flotante, para que un valor matemáticamente
exacto en una frontera no quede mal clasificado.

### Recomendador

`backend/src/recomendador.py` es el primer módulo que coordina varias fuentes de
datos y, opcionalmente, escribe en Supabase (RF-05). Expone tres funciones con
responsabilidades separadas:

| Función | Rol |
|---|---|
| `calcular_recomendaciones(productos, proveedores, producto_proveedor, historial_demanda, parametros=None, periodos_por_año=12, dias_por_periodo=30, margen_seguridad_pct=0.20)` | Función **pura**: recibe cuatro DataFrames y devuelve el DataFrame de recomendaciones. Orquesta los seis módulos del motor. |
| `generar_recomendaciones(supabase_client)` | Solo entrada/salida: lee las cuatro tablas de datos más `parametros_configuracion`, normaliza los nombres de columna (`id` → `producto_id`/`proveedor_id`, `nombre` → `proveedor_nombre`) y delega el cálculo en la función pura. |
| `guardar_recomendaciones(supabase_client, recomendaciones)` | Solo entrada/salida: inserta en la tabla `recomendaciones` y devuelve las filas persistidas con los `id` (uuid) que generó Supabase. |

En una línea, lo que hace el cálculo: filtra los productos válidos (al menos 2
periodos de historial, al menos una relación con proveedor y CV calculable),
clasifica ABC y XYZ, estima la demanda, elige por producto el proveedor de mayor
score (y menor precio en caso de empate), calcula EOQ, stock de seguridad y
punto de reorden, evalúa el ahorro por volumen y marca la urgencia por riesgo de
quiebre (Crítico / Atención / Sin riesgo). Ordena la salida por urgencia, luego
por ahorro neto descendente y, como desempate final, por `producto_id`
ascendente. Los productos que no cumplen los requisitos se descartan en
silencio; los `ValueError` del motor se propagan sin capturar.

La salida tiene 28 columnas, que incluyen tanto los datos del producto y del
proveedor elegido como los cálculos del motor y el snapshot necesario para
trazabilidad (`lead_time_dias`, `precio_unitario`). El detalle completo del
algoritmo y de los casos borde está en el docstring del módulo.

Cómo se usa hoy: `python scripts/demo_recomendador.py` (reporte de
recomendaciones) y `python scripts/demo_flujo_completo.py` (reporte completo más
evaluación).

### Evaluador

`backend/src/evaluador.py` es la última pieza del pipeline (RF-06): aplica la
rúbrica de 6 criterios de `MVP.md` §10 a las recomendaciones **ya persistidas**.
Expone tres funciones:

| Función | Rol |
|---|---|
| `evaluar_recomendaciones(recomendaciones, parametros=None)` | Función **pura**: recibe un DataFrame con una fila por recomendación y devuelve un DataFrame con 6 filas por recomendación (una por criterio). |
| `guardar_evaluaciones(supabase_client, evaluaciones)` | Solo entrada/salida: inserta en `evaluaciones_criterios`. |
| `evaluar_y_guardar(supabase_client, recomendaciones, parametros=None)` | Conveniencia: evalúa y guarda en una sola llamada. |

Criterios aplicados, con el valor que se guarda en `valor_numerico`:

| # | Criterio | Estados posibles | `valor_numerico` |
|---|---|---|---|
| 1 | `riesgo_quiebre_stock` | Crítico / Atención / Sin riesgo | `stock_actual` |
| 2 | `eficiencia_cantidad_eoq` | Pedido muy pequeño / Óptima / Pedido excesivo | `cantidad_recomendada / cantidad_eoq` |
| 3 | `confianza_demanda` | Alta confianza / Confianza moderada / Baja confianza (revisión manual) | `cv_demanda` |
| 4 | `importancia_producto` | Alta / Media / Baja | nulo |
| 5 | `confiabilidad_proveedor` | Confiable / Aceptable con reservas / Riesgoso | `score_proveedor` |
| 6 | `oportunidad_ahorro` | Ahorro detectado / Sin oportunidad adicional | `ahorro_neto_estimado` |

Contrato relevante: el DataFrame de entrada debe traer `recomendacion_id` (el
uuid que Supabase asignó al insertar la recomendación). El evaluador **no genera
ni resuelve identificadores**: si son nulos o inválidos, el `insert` fallará por
clave foránea en `db/schema.sql`. En la práctica esto obliga a persistir las
recomendaciones antes de evaluarlas, y es la razón de que el flujo completo pase
por Supabase. El orden lógico de los criterios (`ORDEN_CRITERIOS`) coincide con
el `check` de la tabla, pero no se guarda como columna: ver `PENDIENTES.md`.

### Configurabilidad

`backend/src/config.py` es el **único punto de entrada** de los umbrales:

- `PARAMETROS_DEFAULT` es la fuente única de verdad de los valores por defecto, y
  de ahí los toman los módulos del motor para los defaults de sus firmas.
- `cargar_parametros(supabase_client)` lee la tabla `parametros_configuracion`, la
  aplana a `{nombre: float}`, exige los 10 parámetros esperados (si falta alguno
  lanza `ValueError`, incluida una tabla vacía) y devuelve también cualquier
  parámetro extra que aparezca en la tabla. Importar el módulo no se conecta a
  Supabase.
- Ningún módulo del motor lee de Supabase: `generar_recomendaciones` carga los
  parámetros y los pasa ya resueltos a `calcular_recomendaciones`, y el evaluador
  recibe los suyos por su parámetro `parametros`.

Los 10 parámetros y el punto donde se consumen:

| Parámetro | Valor por defecto | Consumido por |
|---|---|---|
| `abc_clase_a_pct` | 80 | `umbral_clase_a` de `clasificar_abc` |
| `abc_clase_b_pct` | 95 | `umbral_clase_b` de `clasificar_abc` |
| `ahorro_neto_min_pct` | 3 | `umbral_ahorro_pct` de `calcular_ahorro` |
| `cv_confianza_alta` | 0.5 | `umbral_x` de `clasificar_xyz` y corte del criterio 3 |
| `cv_confianza_media` | 1.0 | `umbral_y` de `clasificar_xyz` y corte del criterio 3 |
| `demanda_ventana_default` | 6 | `ventana` de `estimar_demanda` (llega como float y se convierte a `int`) |
| `eoq_max_pct` | 110 | `ratio_max` del evaluador (se convierte a fracción) |
| `eoq_min_pct` | 90 | `ratio_min` del evaluador (se convierte a fracción) |
| `score_proveedor_confiable` | 80 | `umbral_confiable` de `calcular_score_proveedor` |
| `score_proveedor_riesgoso` | 60 | `umbral_riesgoso` de `calcular_score_proveedor` |

Cambiar un umbral es un `UPDATE` sobre `parametros_configuracion` (ver el ejemplo
en `README.md`) y surte efecto en la siguiente corrida del motor, sin tocar
código. La configurabilidad end-to-end está verificada: bajar `abc_clase_a_pct`
de 80 a 50 cambió la clase ABC de 3 productos y subir `ahorro_neto_min_pct` de 3
a 10 redujo a 0 los productos con "Ahorro detectado". Esa verificación está
registrada en `PENDIENTES.md`.

Lo que **no** es configurable hoy (valores en constantes de módulo, por decisión
de alcance): los periodos por año y el margen de seguridad de `eoq_rop.py`, los
periodos por año de `ahorro.py`, los pesos `PESO_CUMPLIMIENTO` y `PESO_CALIDAD`
de `proveedor.py`, `MIN_PERIODOS` de `xyz.py` y las etiquetas de urgencia del
recomendador. El listado y el motivo están en `PENDIENTES.md`.

---

## Lo que falta

Falta toda la capa de interacción. El sistema calcula, evalúa y persiste, pero se
opera desde scripts de terminal: no hay forma de cargar datos sin SQL manual, de
preguntar en lenguaje natural ni de ver la cola de recomendaciones en pantalla.
Por eso los criterios de aceptación 1, 4, 5, 6 y 8 de `MVP.md` §15 todavía no se
cumplen.

### Agente conversacional

Pendiente (RF-09 y RF-10, `MVP.md` §12). El paquete
`backend/src/agente/` existe, pero está vacío: no hay funciones de consulta, ni
integración con la API del LLM, ni grounding, ni la restricción de solo lectura
implementada en código. Lo único verificado es que la conexión con el proveedor
de LLM (Z.ai / GLM) funciona, mediante `scripts/verificar_zai.py`. Las cinco
funciones de solo lectura que define el MVP (`buscar_recomendaciones`,
`detalle_recomendacion`, `explicar_criterio`, `comparar_proveedores`,
`resumen_prioridad_ABC_XYZ`) están especificadas pero no implementadas. Esto no
bloquea al resto del sistema: el motor y el evaluador no dependen del agente.

### Frontend

Pendiente (RF-07, RF-08 y RF-12, `MVP.md` §13). No existe el directorio
`frontend/`: no hay proyecto Vue 3, ni cola de recomendaciones, ni panel de
explicabilidad, ni vista de proveedores, ni chat, ni panel de KPIs, ni pantalla
de inicio de sesión con Supabase Auth. El backend ya deja los datos listos para
esa capa: `recomendaciones` y `evaluaciones_criterios` se pueden leer con la
`anon key` gracias a las políticas de solo lectura, y el `check` de la tabla
limita los criterios a los 6 previstos. Queda un pendiente de diseño menor para
esa fase: la tabla no guarda el orden lógico de los criterios (ver
`PENDIENTES.md`).

### Script de ingesta

Pendiente (RF-01, `MVP.md` §8.3). El paquete `backend/src/ingesta/`
existe, pero está vacío. Hoy los datos se cargan ejecutando `db/schema.sql` y
`db/seed_sintetico.sql` a mano en el SQL Editor de Supabase. Falta el script que
lea CSV/Excel con pandas, valide columnas y campos clave e inserte en Supabase
con la `service_role key`. El motor no depende del formato de origen (requisito
no funcional de `MVP.md` §7), así que implementarlo no exige cambios en los
módulos existentes.

---

## Cómo verificar el estado actual

Los comandos suponen partir de la raíz del repositorio y tener Python 3.11+.

**1. Instalar dependencias:**

```bash
cd backend && pip install -r requirements.txt
```

Instala `supabase`, `python-dotenv`, `openai`, `pandas`, `numpy` y `pytest`.

**2. Correr los tests** (no requiere Supabase ni `.env`):

```bash
cd backend
python -m pytest -q
```

Esperado: `403 passed`, en unos 5 segundos.

**3. Correr el script de demo** (requiere `.env` configurado con `SUPABASE_URL` y
`SUPABASE_SERVICE_ROLE_KEY`, y el seed ya cargado en Supabase):

```bash
python scripts/demo_flujo_completo.py
```

Esperado: 6 recomendaciones generadas y, en el resumen, 0 "Crítico", 1
"Atención", 5 "Sin riesgo", 2 con "Ahorro detectado" y una suma de ahorro neto de
1.869,75. El script es **interactivo**: al final pregunta si guardar en Supabase.
Si se responde "S", escribe en `recomendaciones`, cruza los uuid generados y
guarda las **36 evaluaciones** (6 recomendaciones × 6 criterios) en
`evaluaciones_criterios`; si se responde "N", solo imprime el reporte y no escribe
nada. Para obtener las 36 evaluaciones la tabla `recomendaciones` debe estar vacía
(al cierre de este documento lo estaba); con corridas anteriores acumuladas el
script lo advierte antes de escribir.

**4. Verificar el entorno** (los tres requieren `.env` configurado):

```bash
python scripts/verificar_rls.py
python scripts/verificar_service_role.py
python scripts/verificar_zai.py
```

Esperado: los tres terminan sin errores. Verifican, respectivamente, que `anon`
solo puede leer, que `service_role` puede escribir y que la API del LLM responde.

---

## Referencias

- Ver `MVP.md` para la especificación del producto (alcance, requisitos,
  rúbrica de 6 criterios y modelo de datos).
- Ver `README.md` para setup e instalación.
- Ver `VERIFICACION.md` para la guía de verificación del sistema (comandos y
  resultados esperados nivel por nivel).
- Ver `PENDIENTES.md` para deuda técnica y `DECISIONES_DISENO.md` para las
  decisiones de diseño.
- Ver `PRD_Sistema_Optimizacion_Compras.md` para el documento de requisitos
  original.
- Ver `db/schema.sql` y `db/seed_sintetico.sql` para el esquema y los datos de
  prueba.
