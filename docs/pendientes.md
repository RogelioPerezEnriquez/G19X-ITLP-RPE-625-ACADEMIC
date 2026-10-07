# Pendientes técnicos

Este archivo registra decisiones que quedan abiertas, deuda técnica, y
aspectos a revisar antes de cerrar el MVP.

Para decisiones de diseño, ver `docs/decisiones-diseno.md`.

## Deuda técnica

- [ ] **Configurabilidad completa de parámetros** (post-MVP)
      - La tabla `parametros_configuracion` tiene 10 filas.
        Los parámetros configurables son: `abc_clase_a_pct`, `abc_clase_b_pct`,
        `ahorro_neto_min_pct`, `cv_confianza_alta`, `cv_confianza_media`,
        `demanda_ventana_default`, `eoq_max_pct`, `eoq_min_pct`,
        `score_proveedor_confiable`, `score_proveedor_riesgoso`.
      - Los siguientes parámetros NO están en la tabla y por decisión de
        alcance siguen hardcodeados:
        - `eoq_rop.py`: `PERIODOS_POR_AÑO_DEFAULT`, `DIAS_POR_PERIODO_DEFAULT`,
          `MARGEN_SEGURIDAD_PCT_DEFAULT`.
        - `proveedor.py`: `PESO_CUMPLIMIENTO`, `PESO_CALIDAD`.
        - `xyz.py`: `MIN_PERIODOS`.
        - `ahorro.py`: `PERIODOS_POR_AÑO_DEFAULT`.
        - `recomendador.py`: `URGENCIA_*`.
      - Si en el futuro se quiere configurabilidad total, añadir esos
        parámetros a la tabla.

- [ ] **Validar `float('inf')` en `ahorro.py`** (menor)
      - Actualmente `umbral_ahorro_pct = float('inf')` pasa la validación
        (solo se rechaza NaN y negativos).
      - Con `inf`, cualquier `ahorro_neto` queda "Sin oportunidad adicional".
      - Corregir añadiendo `math.isinf` a la validación.

- [ ] **Validar `NaN`/`inf` en `eoq_rop.py`** (menor)
      - Análogo al caso anterior pero para `margen_seguridad_pct`.
      - El docstring ya documenta el comportamiento, pero el código sigue
        aceptando esos valores y produce SS/ROP en NaN/inf.

- [ ] **Ajustar el seed para alinear clases ABC/XYZ con el diseño original**
      (opcional, después del MVP)
      - `SEED_Engrane G7`: diseño A/Z, real A/Y.
      - `SEED_Widget B`: diseño A/Y, real A/X.
      - `SEED_Cable HDMI`: diseño C/Z, real C/Y.
      - `SEED_Pintura 1L`: diseño C/Y, real A/X.
      - Motivo: el seed se diseñó con estimaciones a ojo de la variabilidad
        (CV). El motor calcula los CV reales, que resultan más bajos.

- [ ] **Revisar `stock_actual` del seed para generar al menos un "Crítico"**
      (opcional, para la demo)
      - Actualmente ningún producto cae en "Crítico" con los datos del seed.
      - Ajustar el `stock_actual` de algún producto para que
        `stock_actual <= stock_seguridad`.

- [ ] **Orden lógico de criterios al leer de Supabase** (menor)
      - La tabla no guarda el orden lógico de los criterios.
      - El frontend debe ordenar por criterio con un CASE, o se añade un
        campo `orden_criterio` a `evaluaciones_criterios`.
      - Revisar cuando se implemente el panel de explicabilidad.

- [ ] **Replicar test guardián de constantes en los módulos del motor** (post-MVP)
      - Actualmente solo `evaluador.py` tiene un test que verifica que las
        constantes migradas no vuelvan al módulo.
      - Replicar en `xyz.py`, `abc.py`, `demanda.py`, `proveedor.py`,
        `ahorro.py`.
      - Bajo costo, previene regresiones.

- [ ] **Múltiples recomendaciones por producto** (post-MVP)
      - La tabla `recomendaciones` no tiene constraint único por
        `producto_id`, así que cada corrida del pipeline agrega filas.
      - Las tools del agente devuelven "la más reciente" en los casos
        de detalle, pero `buscar_recomendaciones` y `resumen_*`
        cuentan duplicados si hay varias corridas.
      - Solución a futuro: añadir un campo `activa` (boolean) y filtrar
        por él, o añadir un constraint único por (producto_id, activa).

- [ ] **Policy de UPDATE para `parametros_configuracion`** (fase frontend)
      - Actualmente solo tiene policy de SELECT para anon/authenticated.
      - El criterio de aceptación 8 requiere que solo admins puedan
        modificar parámetros.
      - Resolver al implementar la pantalla de configuración (fase 6).

- [ ] **Cumplir RF-12: sin registro público** (post-MVP, opcional)
      - Actualmente el frontend tiene registro abierto (RegisterView).
      - RF-12 pide "sin registro público de usuarios; las pantallas de
        login sin opción de registro".
      - Para cumplir: desactivar el registro en Supabase Auth y
        eliminar RegisterView + el link en LoginView.
      - Decisión documentada en docs/decisiones-diseno.md (D-14). 

- [ ] **Ajustar el seed para cubrir el estado "Riesgoso"** (opcional)
      - `SEED_RiesgoTotal` tiene valores `(50, 25)` que dan score 60.0
        → "Aceptable con reservas".
      - Para que sea "Riesgoso" (score < 60), ajustar a:
        - `(40, 30)`: score 52.0 → Riesgoso.
        - `(45, 25)`: score 57.0 → Riesgoso.
      - Requiere recargar el seed + re-ejecutar el pipeline.
      - Hacer al final, si se quiere una demo con los 3 estados.           

## Resueltos

- [x] **Agente conversacional (RF-09, RF-10)**
      - 5 tools de solo lectura en `backend/src/agente/tools.py`.
      - Cliente LLM con function calling en
        `backend/src/agente/llm_client.py`.
      - Esquema de tools en `backend/src/agente/tools_schema.py`.
      - Grounding verificado con el LLM real (Z.ai): el agente responde
        con datos reales y rechaza responder cuando no los tiene.
      - RF-10 verificado: indica explícitamente cuando no hay datos.
      - Restricción de solo lectura: usa `SUPABASE_ANON_KEY`.
      - Script de verificación manual en
        `scripts/verificar_agente_rapido.py`.

- [x] **Script de ingesta desde CSV/Excel a Supabase (RF-01)**
      - Script en `backend/src/ingesta/cargar_dataset.py`.
      - CLI en `backend/src/ingesta/__main__.py`.
      - Carga 4 tablas: productos, proveedores, producto_proveedor,
        historial_demanda.
      - Resuelve las FKs por nombre (los CSVs usan nombres legibles, no
        UUIDs).
      - Valida que las tablas estén vacías antes de insertar (evita
        duplicidad).
      - Normaliza fechas a ISO y tipos numéricos antes de insertar.
      - CSVs de ejemplo en `data/raw/`.

- [x] **Auditoría de docstrings y corrección de hallazgos**
      - Auditoría completa de los 9 módulos de producción (con AST parsing,
        referencias cruzadas a docs/mvp.md, PRD, schema.sql y documentación interna).
      - 32 hallazgos detectados, clasificados por tipo e impacto:
        * 2 errores reales (indentación rota, afirmación falsa).
        * 7 referencias obsoletas (numeración de pasos, frases sobre la
          tabla de configuración "que se iba a incorporar" cuando ya existe).
        * 3 faltantes (comportamiento de NaN/inf no documentado).
        * 9 sugerencias de bajo impacto.
        * 11 inconsistencias de estilo (transversales).
      - 9 hallazgos corregidos (los de impacto alto/medio + los baratos).
      - 23 hallazgos revisados y descartados (inconsistencias de estilo
        consistentes por familia de módulos, sugerencias cosméticas).

- [x] **Limpiar referencias obsoletas a constantes migradas**
      - `config.py`: eliminadas 10 referencias a constantes obsoletas
        (`UMBRAL_CLASE_A`, `UMBRAL_CLASE_B`, `UMBRAL_X`, `UMBRAL_Y`,
        `VENTANA_DEFAULT`, `UMBRAL_CONFIABLE`, `UMBRAL_RIESGOSO`,
        `UMBRAL_AHORRO_PCT_DEFAULT`, `RATIO_MIN`, `RATIO_MAX`) y 2 frases
        obsoletas. En su lugar, se dejó un mapeo explícito
        `clave -> parámetro de función` para cada una de las 10 claves.
      - `xyz.py`: eliminadas 2 referencias a `CV_ALTA`/`CV_MODERADA`.
      - `evaluador.py`: ya estaba limpio (referencias eliminadas en el
        commit de parametrización del evaluador).

- [x] **Verificación de referencias obsoletas en todo el repo**
      - Búsqueda exhaustiva de 15 constantes migradas a configuración en
        todos los archivos del repo (excepto `.git`).
      - Resultado: 0 referencias reales en código de producción.
      - Coincidencias encontradas (todas legítimas):
        * Docstrings y comentarios que documentan la eliminación.
        * Alias locales en tests que leen los defaults de `PARAMETROS_DEFAULT`
          o de las firmas (patrón intencional).
        * Test guardián en `test_evaluador.py` que verifica que las constantes
          no vuelvan al módulo.
      - Artefactos binarios (`.pyc`): 0 en `src/`, coincidencias solo en
        `.pyc` de tests (regenerables, no versionados).

- [x] **Parametrización completa de la fase de configurabilidad**
      - Los 5 módulos del motor (abc, xyz, demanda, proveedor, ahorro)
        reciben sus umbrales como parámetros con defaults de
        `config.PARAMETROS_DEFAULT`.
      - El `recomendador.py` lee los parámetros de Supabase y los propaga
        al motor.
      - El `evaluador.py` recibe los parámetros y aplica las conversiones
        de unidades internamente.
      - Cumple con RF-11 (el administrador puede modificar umbrales sin
        tocar código).

- [x] **Unificar validación de columnas entre módulos del motor**
      - `abc.py` era permisivo con DataFrames vacíos sin columnas.
      - Se corrigió para ser estricto como los demás módulos.

- [x] **Acoplamiento de unidades entre `eoq_rop.py` y `ahorro.py`**
      - `recomendador.py` pasa el mismo `periodos_por_año` a ambos módulos.

- [x] **Autenticación con Supabase Auth (parcial)**
      - Login con email/password.
      - Registro (abierto, ver pendiente sobre RF-12).
      - Logout.
      - Store `auth` con `user`, `session`, `isAdmin`, `cargando`.
      - Router guards con `meta.requiresAuth` y `meta.requiresAdmin`.
      - NavBar con estado de sesión y badge "Administrador".
      - Tabla `admins` creada con RLS y policies.
      - Policy de UPDATE en `parametros_configuracion` para admins.
      - Nota: falta la pantalla de configuración de parámetros (fase
        6.7) para completar el criterio 8.
        
- [x] **Cola de recomendaciones (criterio 4)**
      - Vista `RecomendacionesView.vue` en `/recomendaciones`.
      - Store `recomendaciones` con carga desde Supabase.
      - Tarjetas con urgencia (badge de color), clase ABC/XYZ,
        ahorro neto y cantidad recomendada.
      - Filtro por urgencia (cliente, instantáneo).
      - Click en tarjeta navega a `/recomendaciones/:productoId`
        (placeholder, se completa en la fase 6.3).
      - Formato de números en español (con `useGrouping: 'always'`). 

- [x] **Panel de explicabilidad (criterio 5)**
      - Vista `RecomendacionDetalleView.vue` en
        `/recomendaciones/:productoId`.
      - 6 tarjetas de criterios con estado, valor y descripción.
      - Formato español de números.
      - Componente `CriterioCard.vue` reutilizable.
      - Constante `CRITERIOS_ORDENADOS` en
        `constants/criterios.js` con el orden del MVP.

- [x] **Vista de proveedores**
      - Vista `ProveedoresView.vue` en `/proveedores`.
      - Store `proveedores` con cálculo de score y estado en el frontend.
      - Componentes `ProveedorCard.vue`, `ScoreBadge.vue`,
        `BarraProgreso.vue`.
      - Coherencia de tolerancia (1e-9) con el backend.     

- [x] **Chat con el agente conversacional**
      - Store `chat` con manejo de mensajes e historial.
      - Vista `/chat` con burbujas de usuario y asistente.
      - Renderizado de Markdown en las respuestas del asistente
        (librerías `marked` + `dompurify`).
      - Botones de sugerencia, indicador "escribiendo...", auto-scroll.
      - API FastAPI que expone el agente (`backend/src/agente/api.py`).
      - Script para levantar el servidor (`scripts/run_api.py`).
      - Prompt del sistema usa pesos mexicanos (`$`).         

## Notas de configurabilidad

- **`config.py` es el único punto de entrada de parámetros.** Ningún módulo
  del motor lee directamente de Supabase. El `recomendador.py` carga los
  parámetros y los pasa a cada módulo como argumento.

- **`PARAMETROS_DEFAULT` es la fuente única de verdad de los defaults.**
  Los módulos importan de aquí.

- **`cargar_parametros` valida que estén los 10 parámetros.** Si falta
  alguno, lanza `ValueError`.

- **Unidades**: los `*_pct` están en porcentaje. `eoq_min_pct` y
  `eoq_max_pct` requieren conversión a fracción (÷100) antes de pasarlos
  al evaluador. `demanda_ventana_default` requiere conversión a int antes
  de pasarlo a `demanda.py`.

- **`cargar_parametros` no filtra claves extra**: si la tabla trae
  parámetros nuevos que no están en `PARAMETROS_DEFAULT`, se devuelven
  también. Esto permite añadir parámetros a la tabla sin tocar `config.py`.

## Notas de integración

- **Verificación end-to-end del agente**: se verificó el agente
  conversacional contra el LLM real (Z.ai) con 7 preguntas:
  - Consulta general (conteos por urgencia, resumen).
  - Pregunta de seguimiento (manejo de historial).
  - Producto inexistente (RF-10).
  - Productos en atención (filtrado).
  - Detalle de un producto (grounding).
  - Comparación de proveedores (grounding).
  - Resumen de prioridades ABC/XYZ.
  El agente respondió con datos reales en todos los casos y rechazó
  responder cuando no había datos.

- **Verificación end-to-end de configurabilidad (RF-11)**: se verificó que
  los parámetros de `parametros_configuracion` afectan los resultados del
  motor:
  - Prueba 1: bajar `abc_clase_a_pct` de 80 a 50 cambió la clase ABC de 3
    productos (Widget B, Pintura 1L, Widget A pasaron de A a B).
  - Prueba 2: subir `ahorro_neto_min_pct` de 3 a 10 redujo los productos
    con "Ahorro detectado" de 2 a 0.
  - Restauración: los 10 parámetros se restauraron a sus valores originales
    y las tablas `recomendaciones`/`evaluaciones_criterios` quedaron vacías.

- **Verificación end-to-end exitosa (recomendador)**: el recomendador
  funciona con los datos reales del seed. Se generaron 6 recomendaciones:
  - Atención: 1 (SEED_Engrane G7)
  - Sin riesgo: 5
  - Crítico: 0
  - Con "Ahorro detectado": 2 (Engrane G7, Tornillo M3)
  - Suma total de ahorro neto: $1,869.75

- **Verificación end-to-end completa (recomendador + evaluador)**: el
  flujo completo funciona con datos reales. Se generan:
  - 6 recomendaciones (una por producto del seed).
  - 36 evaluaciones (6 recomendaciones × 6 criterios).

- **Discrepancias entre diseño del seed y resultados reales**: las clases
  ABC/XYZ calculadas por el motor no coinciden exactamente con las que se
  diseñaron al crear el seed. El motivo está documentado en la sección de
  deuda técnica.

- **Ninguna recomendación cae en "Crítico"**: era esperado con los stocks
  actuales del seed. Documentado en deuda técnica.

- **Orden de los criterios en la tabla**: al insertar en
  `evaluaciones_criterios`, el orden lógico (`ORDEN_CRITERIOS`) se pierde.
  El dashboard de Supabase los muestra en orden arbitrario (a veces
  alfabético). Si el frontend quiere mostrarlos en orden lógico, debe
  hacer un ORDER BY con CASE o guardar un campo `orden_criterio`.

## Casos conocidos y documentados

- **`descuento_pct = 0` en `ahorro.py`**: si un proveedor declara
  `cantidad_umbral_descuento` con `descuento_pct = 0`, el módulo sube el
  pedido al umbral sin obtener ahorro. Es una asimetría del contrato: el
  módulo nunca baja el pedido, pero sí lo sube si hay umbral declarado.
  El caso es raro en la práctica (nadie ofrece 0% de descuento) y no
  aparece en el seed.

- **El prorrateo del costo extra hace el criterio 6 más permisivo**:
  revisar las expectativas del seed para el criterio 6 en la fase de
  integración.