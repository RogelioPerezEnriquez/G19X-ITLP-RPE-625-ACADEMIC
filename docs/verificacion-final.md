# Verificación final del MVP

**Fecha**: 13 de octubre de 2026
**Commit de referencia**: `7d14c66591c4c3d7d34a83d3230c45e687c4bbd7` (`7d14c66`)
**Rama**: `main`

Este documento verifica que los 8 criterios de aceptación de
`docs/mvp.md` §15 se cumplen con el sistema completo. Los requisitos se
citan textualmente del MVP; la evidencia se toma de
`docs/estado-implementacion.md`, `docs/pendientes.md` y
`docs/verificacion.md`.

## Resumen

| # | Criterio | Estado |
|---|---|---|
| 1 | Script de ingesta | ✅ |
| 2 | Motor (ABC, XYZ, EOQ, SS, ROP) | ✅ |
| 3 | Recomendaciones con 6 criterios en `evaluaciones_criterios` | ✅ |
| 4 | Cola de recomendaciones priorizada en la interfaz | ✅ |
| 5 | Panel de explicabilidad con los 6 criterios | ✅ |
| 6 | Agente grounded que rechaza responder sin datos | ✅ |
| 7 | Umbral modificable sin tocar código | ✅ |
| 8 | Usuario sin admin no accede a configuración | ✅ |

## Criterio 1 — Script de ingesta

**Requisito**: «El script de ingesta carga el dataset sintético en
Supabase sin errores de validación.»

**Cómo se verificó**: se ejecutó el CLI de ingesta
(`backend/src/ingesta/cargar_dataset.py` + `backend/src/ingesta/__main__.py`)
contra los CSVs de ejemplo de `data/raw/`:

```bash
python backend/src/ingesta/__main__.py
# o, desde backend/:
python -m src.ingesta
```

El script carga las 4 tablas de datos (productos, proveedores,
producto_proveedor, historial_demanda), resuelve las claves foráneas por
nombre, normaliza fechas a ISO y tipos numéricos, valida columnas
requeridas, nulos, claves duplicadas y referencias huérfanas antes de
insertar, y exige que las tablas estén vacías (no borra ni sobrescribe).
Al terminar imprime el conteo de filas insertadas por tabla.

**Resultado**: ✅

**Evidencia**:
- Comando: `python backend/src/ingesta/__main__.py` (código de salida 0;
  conteo de filas por tabla).
- Registrado como resuelto (RF-01) en `docs/pendientes.md` §Resueltos y
  marcado «✅ Completo» en `docs/estado-implementacion.md` (tabla de
  estado por componente).
- Archivos: `backend/src/ingesta/cargar_dataset.py`,
  `backend/src/ingesta/__main__.py`, CSVs en `data/raw/`
  (`productos.csv`, `proveedores.csv`, `producto_proveedor.csv`,
  `historial_demanda.csv`).

## Criterio 2 — Motor

**Requisito**: «El motor calcula ABC, XYZ, EOQ, stock de seguridad y ROP
para todos los productos.»

**Cómo se verificó**: dos vías.

1. Suite de tests unitarios (inyectan DataFrames sintéticos, sin red ni
   base de datos):

   ```bash
   cd backend
   python -m pytest -q
   ```

   Esperado: `451 passed` (254 de los 451 tests corresponden a los 6
   módulos del motor: `abc.py`, `xyz.py`, `demanda.py`, `eoq_rop.py`,
   `proveedor.py`, `ahorro.py`).

2. Corrida end-to-end contra el seed real en Supabase:

   ```bash
   python scripts/demo_flujo_completo.py
   ```

   Esperado: 6 recomendaciones generadas (una por producto del seed), cada
   una con `clase_abc`, `clase_xyz`, `cantidad_eoq`, `stock_seguridad` y
   `punto_reorden` calculados. Resumen observado: 0 «Crítico», 1
   «Atención», 5 «Sin riesgo», 2 con «Ahorro detectado», suma de ahorro
   neto $1.869,75.

**Resultado**: ✅

**Evidencia**:
- Comandos anteriores y tabla de resultados observados en
  `docs/estado-implementacion.md` §Métricas del proyecto.
- Corrida end-to-end del recomendador registrada en `docs/pendientes.md`
  §Notas de integración («Verificación end-to-end exitosa»).
- Procedimiento reproducible en `docs/verificacion.md` (Niveles 1 y 3).
- Nota: `docs/verificacion.md` registra 403 tests porque se verificó
  sobre un commit anterior (`23b134b`, 30/09/2026); la cifra vigente
  es 451 (verificado sobre el estado actual de la rama `main`, en
  `docs/estado-implementacion.md`).


## Criterio 3 — Recomendaciones con los 6 criterios evaluados

**Requisito**: «Se generan recomendaciones con los 6 criterios evaluados
y almacenados en `evaluaciones_criterios`.»

**Cómo se verificó**: corrida de `python scripts/demo_flujo_completo.py`
respondiendo «S» en la pregunta interactiva de guardado. El script
persiste las 6 recomendaciones en `recomendaciones`, cruza los uuid
generados y guarda las evaluaciones del evaluador
(`backend/src/evaluador.py`, que aplica la rúbrica de 6 criterios de
`docs/mvp.md` §10). Verificación posterior en el SQL Editor de Supabase:

```sql
SELECT count(*) FROM evaluaciones_criterios;
-- Esperado: 36  (6 recomendaciones × 6 criterios)

SELECT criterio, count(*) FROM evaluaciones_criterios GROUP BY criterio;
-- Esperado: 6 filas por cada uno de los 6 criterios:
-- riesgo_quiebre_stock, eficiencia_cantidad_eoq, confianza_demanda,
-- importancia_producto, confiabilidad_proveedor, oportunidad_ahorro
```

**Resultado**: ✅

**Evidencia**:
- Comando: `python scripts/demo_flujo_completo.py` (guardando en
  Supabase) + consultas SQL anteriores.
- Registrado en `docs/pendientes.md` §Notas de integración
  («Verificación end-to-end completa (recomendador + evaluador): 6
  recomendaciones, 36 evaluaciones»).
- El evaluador tiene 76 tests (`backend/tests/test_evaluador.py`) dentro
  de la suite de 451.

## Criterio 4 — Cola de recomendaciones priorizada

**Requisito**: «La cola de recomendaciones se muestra priorizada en la
interfaz.»

**Cómo se verificó**: levantando el frontend (`cd frontend && npm run
dev`, Vite en `http://localhost:5173`) y abriendo la vista
`/recomendaciones` (`RecomendacionesView.vue`). La vista lee
`recomendaciones` desde Supabase y muestra tarjetas
(`RecomendacionCard.vue`) con badge de urgencia por color
(`UrgenciaBadge.vue`), clase ABC/XYZ, ahorro neto y cantidad
recomendada, con filtro por urgencia. La priorización (urgencia, luego
ahorro neto descendente, luego `producto_id`) la fija el recomendador al
ordenar la salida.

**Resultado**: ✅

**Evidencia**:
- Implementación y verificación registradas en `docs/pendientes.md`
  §Resueltos («Cola de recomendaciones») y «Correcciones de la
  verificación end-to-end» (ajustes surgidos del recorrido con la UI).
- Componentes: `frontend/src/views/RecomendacionesView.vue`,
  `frontend/src/components/RecomendacionCard.vue`,
  `frontend/src/components/UrgenciaBadge.vue`,
  `frontend/src/stores/recomendaciones.js`.
- Ver la observación 1 al final de este documento sobre el estado del
  recorrido end-to-end formal con la UI.

## Criterio 5 — Panel de explicabilidad

**Requisito**: «El panel de explicabilidad muestra los 6 criterios con
estado y valor.»

**Cómo se verificó**: desde la cola de recomendaciones, clic en una
tarjeta para abrir `/recomendaciones/:productoId`
(`RecomendacionDetalleView.vue`). La vista lee `evaluaciones_criterios`
para esa recomendación y muestra 6 tarjetas (`CriterioCard.vue`), una
por criterio, cada una con estado, valor numérico y descripción, en el
orden lógico del MVP (constante `CRITERIOS_ORDENADOS` en
`frontend/src/constants/criterios.js`, necesario porque la tabla no
guarda el orden de los criterios).

**Resultado**: ✅

**Evidencia**:
- Implementación y verificación registradas en `docs/pendientes.md`
  §Resueltos («Panel de explicabilidad (criterio 5)»).
- Componentes: `frontend/src/views/RecomendacionDetalleView.vue`,
  `frontend/src/components/CriterioCard.vue`,
  `frontend/src/constants/criterios.js`.
- Los 6 criterios y sus estados posibles están definidos en
  `docs/mvp.md` §10 y los escribe `backend/src/evaluador.py` (criterio
  3 de este documento).

## Criterio 6 — Agente grounded que rechaza responder sin datos

**Requisito**: «El agente responde preguntas sobre recomendaciones
citando datos reales y **rechaza responder cuando no tiene datos**.»

**Cómo se verificó**: verificación end-to-end del agente contra el LLM
real (Z.ai / GLM) con 7 preguntas: consulta general (conteos por
urgencia), pregunta de seguimiento (historial), producto inexistente
(RF-10), productos en atención (filtrado), detalle de un producto
(grounding), comparación de proveedores (grounding) y resumen de
prioridades ABC/XYZ. Además, el chat se probó desde la interfaz
(`/chat`, con la API del agente levantada con
`python scripts/run_api.py`). Existe además un script de verificación
manual (`python scripts/verificar_agente_rapido.py`).

**Resultado**: ✅

**Evidencia**:
- Registrado en `docs/pendientes.md` §Notas de integración
  («Verificación end-to-end del agente»: «respondió con datos reales en
  todos los casos y rechazó responder cuando no había datos») y
  §Resueltos («RF-10 verificado: indica explícitamente cuando no hay
  datos»).
- Grounding por diseño: las 5 tools son de solo lectura
  (`backend/src/agente/tools.py`, con `SUPABASE_ANON_KEY`) y toda
  respuesta se basa en el resultado de una función consultada.
- 24 tests de tools (`backend/tests/test_tools.py`) y 18 del cliente LLM
  (`backend/tests/test_llm_client.py`) dentro de la suite de 451.

## Criterio 7 — Umbral modificable sin tocar código

**Requisito**: «El administrador puede modificar un umbral en
`parametros_configuracion` y el cambio se refleja sin tocar código.»

**Cómo se verificó**: verificación end-to-end de configurabilidad
(RF-11) en dos pruebas, modificando la tabla desde el SQL Editor de
Supabase y re-corriendo el pipeline sin cambiar código:

Prueba 1:

```sql
UPDATE parametros_configuracion
SET valor = 50
WHERE nombre_parametro = 'abc_clase_a_pct';
```

```bash
python scripts/demo_flujo_completo.py
```

Resultado: 3 productos cambiaron de clase A a B (`SEED_Widget B`,
`SEED_Pintura 1L`, `SEED_Widget A`). El resto del reporte no cambió (el
umbral ABC solo mueve la clasificación).

Prueba 2:

```sql
UPDATE parametros_configuracion
SET valor = 10
WHERE nombre_parametro = 'ahorro_neto_min_pct';
```

```bash
python scripts/demo_flujo_completo.py
```

Resultado: los productos con «Ahorro detectado» bajaron de 2 a 0 (el
umbral es más estricto); los montos de ahorro no cambiaron.

Restauración: los 10 parámetros volvieron a sus valores originales
(existe el script `db/restaurar_parametros.sql`) y las tablas
`recomendaciones`/`evaluaciones_criterios` quedaron vacías.

Además, el administrador puede hacer el mismo cambio desde la interfaz:
la vista `/configuracion` (`ConfiguracionView.vue` + store
`configuracion`) carga y actualiza los 10 parámetros.

**Resultado**: ✅

**Evidencia**:
- Registrado en `docs/pendientes.md` §Notas de integración
  («Verificación end-to-end de configurabilidad (RF-11)»).
- Procedimiento reproducible en `docs/verificacion.md` (Nivel 4).
- Mecanismo: `backend/src/config.py` es el único punto de entrada;
  `cargar_parametros` lee la tabla en cada corrida y el recomendador
  propaga los valores al motor y al evaluador como argumentos.



## Criterio 8 — Usuario sin admin no accede a configuración

**Requisito**: «Un usuario no autenticado o sin rol Administrador no
puede acceder a la pantalla de configuración de parámetros.»

**Cómo se verificó**: recorrido por la interfaz con los dos casos
(usuario no autenticado y usuario autenticado sin rol Administrador),
más la verificación de las barreras de seguridad en tres capas:

1. **Router del frontend** (`frontend/src/router/index.js`): la ruta
   `/configuracion` tiene `meta: { requiresAuth: true, requiresAdmin:
   true }`; el guard redirige a login si no hay sesión y a home si el
   usuario no es admin (`if (to.meta.requiresAdmin && !authStore.isAdmin)
   return { name: 'home' }`).
2. **NavBar**: el enlace a Configuración solo se muestra a admins (badge
   «Administrador» en la barra).
3. **Base de datos (defensa en profundidad)**: la policy
   `solo_admins_actualizan_parametros` restringe el `UPDATE` de
   `parametros_configuracion` a admins, de modo que aunque un usuario
   sin rol llegara a la vista no podría persistir cambios. Además,
   `python scripts/verificar_rls.py` confirma que la `anon key` no puede
   escribir en las tablas (RLS bloquea el `INSERT` de prueba).

**Resultado**: ✅

**Evidencia**:
- Implementación registrada en `docs/pendientes.md` §Resueltos
  («Configuración de parámetros (criterio 8)»: ruta protegida con
  `meta.requiresAdmin`, link del NavBar visible solo para admins, policy
  `solo_admins_actualizan_parametros`) y («Autenticación»: store `auth`
  con `isAdmin`, router guards, tabla `admins` con RLS).
- Código: `frontend/src/router/index.js`, `frontend/src/stores/auth.js`,
  `frontend/src/views/ConfiguracionView.vue`.
- Script: `python scripts/verificar_rls.py` (Nivel 2 de
  `docs/verificacion.md`).
- La tabla `admins` y la policy `solo_admins_actualizan_parametros` están
  versionadas en `db/schema.sql` (ver la observación 2 al final de este
  documento, ya resuelta).

## Observaciones (contradicciones no bloqueantes detectadas)

1. **Estado del recorrido end-to-end formal con la UI.**
   `docs/estado-implementacion.md` (8/10/2026, commit `7d7f942`) dice:
   «Queda pendiente únicamente la verificación end-to-end con la
   interfaz gráfica (fase de integración final)». Sin embargo,
   `docs/pendientes.md` registra en §Resueltos las «Correcciones de la
   verificación end-to-end» (textos del Home, símbolo `$` en ahorro
   neto, KPI «Con ahorro detectado» alineado con el criterio 6), lo que
   indica que el recorrido con la UI ya se realizó y produjo ajustes.
   Este documento toma como válida la verificación con UI documentada en
   `docs/pendientes.md`; sería recomendable actualizar
   `docs/estado-implementacion.md` para retirar ese pendiente.

2. **Seguridad de administradores no versionada en el repo — RESUELTA.**
   La tabla `admins` y la policy `solo_admins_actualizan_parametros`
   (criterio 8) ya fueron agregadas a `db/schema.sql`, junto con la
   policy `usuario_ve_su_propio_admin`, de modo que el esquema es
   reproducible desde cero. Esta observación correspondía a una versión
   anterior en la que ese SQL solo existía aplicado directamente en
   Supabase.

## Conclusión

Los 8 criterios de aceptación de `docs/mvp.md` §15 se cumplen: la
ingesta carga el dataset sin errores de validación, el motor calcula
todos los parámetros de inventario para todos los productos, las
recomendaciones se evalúan contra los 6 criterios y se persisten, la
interfaz muestra la cola priorizada y el panel de explicabilidad, el
agente responde con datos reales y rechaza responder sin ellos, los
umbrales se modifican sin tocar código y la configuración está
restringida a administradores. El MVP está completo. Las observaciones
anteriores son de consistencia documental y de versionado del SQL; no
afectan el cumplimiento de los criterios.
