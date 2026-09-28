# Pendientes técnicos

Este archivo registra decisiones que quedan abiertas, deuda técnica, y
aspectos a revisar antes de cerrar el MVP.

## Deuda técnica

- [ ] **Extraer umbrales y parámetros a `parametros_configuracion`** (fase 4)
      - `abc.py`: `UMBRAL_CLASE_A`, `UMBRAL_CLASE_B`.
      - `xyz.py`: `UMBRAL_X`, `UMBRAL_Y`.
      - `demanda.py`: `VENTANA_DEFAULT`.
      - `eoq_rop.py`: `PERIODOS_POR_AÑO_DEFAULT`, `DIAS_POR_PERIODO_DEFAULT`,
        `MARGEN_SEGURIDAD_PCT_DEFAULT`.
      - `proveedor.py`: `UMBRAL_CONFIABLE`, `UMBRAL_RIESGOSO`,
        `PESO_CUMPLIMIENTO`, `PESO_CALIDAD`.
      - `ahorro.py`: `UMBRAL_AHORRO_PCT_DEFAULT`, `PERIODOS_POR_AÑO_DEFAULT`.
      - `recomendador.py`: `ORDEN_URGENCIA`, `URGENCIA_*` (los valores de
        estado se podrían mantener como constantes).
      - Deberán leerse desde Supabase en la fase 4.

- [ ] **Validar `float('inf')` en `ahorro.py`** (menor)
      - Actualmente `umbral_ahorro_pct = float('inf')` pasa la validación
        (solo se rechaza NaN y negativos).
      - Con `inf`, cualquier `ahorro_neto` queda "Sin oportunidad adicional".
      - Corregir añadiendo `math.isinf` a la validación.

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
      - Revisar cuando se implemente el panel de explicabilidad (fase 6).

## Resueltos

- [x] **Unificar validación de columnas entre módulos del motor**
      - `abc.py` era permisivo con DataFrames vacíos sin columnas.
      - Se corrigió para ser estricto como los demás módulos.

- [x] **Acoplamiento de unidades entre `eoq_rop.py` y `ahorro.py`**
      - `recomendador.py` pasa el mismo `periodos_por_año` a ambos módulos.

## Notas de diseño

- **Tolerancias en comparaciones de frontera**: `abc.py`, `xyz.py`,
  `proveedor.py` y `ahorro.py` usan tolerancias para absorber errores de
  punto flotante en cortes exactos:
  - `TOLERANCIA_PCT` (abc.py): 1e-9
  - `TOLERANCIA_CV` (xyz.py): 1e-9
  - `TOLERANCIA_SCORE` (proveedor.py): 1e-9
  - `TOLERANCIA_AHORRO` (ahorro.py): 1e-9

- **Año comercial de 360 días**: `eoq_rop.py` y `ahorro.py` usan 12
  periodos/año y 30 días/periodo por defecto, lo que implica un año de
  360 días. Coherente con la convención de "año comercial" y documentado
  en los docstrings de los módulos.

- **Correcciones de notación en las fórmulas del MVP.md** (`ahorro.py`):
  - El MVP.md escribe `× descuento_pct` sin división por 100.
  - El MVP.md escribe `× costo_mantener_pct_anual` sin división por 100.
  - El MVP.md usa la variable `EOQ_sin_descuento`, que no existe como
    salida de `eoq_rop.py`.
  - Se corrigieron con la interpretación matemáticamente coherente.

- **Lectura B del criterio 6**: se interpreta "Oportunidad de ahorro por
  volumen" como evaluar si vale la pena subir el pedido al umbral de
  descuento, no solo como reportar el caso donde el EOQ natural ya lo
  supera. Justificación: el nombre del criterio sugiere evaluar la
  oportunidad.

- **Ordenamiento por urgencia con `pd.Categorical`**: se usan categorías
  `["Crítico", "Atención", "Sin riesgo"]` con `ascending=True` para
  respetar la jerarquía de negocio. **Nota**: `ascending=True` respeta
  el orden de las categorías; `ascending=False` daría el orden inverso.

- **`recomendador.py`** es la primera pieza que rompe el principio de
  "función pura":
  - `calcular_recomendaciones`: pura (orquesta el motor).
  - `generar_recomendaciones`: I/O (lee de Supabase).
  - `guardar_recomendaciones`: I/O (escribe en Supabase).

- **Exclusiones en `recomendador.py`**: se excluyen silenciosamente los
  productos que:
  - No tienen historial o tienen < 2 periodos.
  - No tienen ningún proveedor en `producto_proveedor`.
  - Tienen `cv_demanda` no calculable (demanda media cero).

## Notas de integración

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

- **Ejemplos numéricos en los prompts deben verificarse con calculadora.**
  Ya hubo un error en `xyz.py` (los CV del ejemplo) que Cline corrigió
  detectando la contradicción.