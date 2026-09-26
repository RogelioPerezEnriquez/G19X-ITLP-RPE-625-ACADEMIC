## Deuda técnica

- [x] **Unificar validación de columnas entre módulos del motor** — resuelto
      - `abc.py` valida las columnas requeridas antes del chequeo de DataFrame
        vacío, así que un DataFrame vacío sin columnas lanza `ValueError` igual
        que `xyz.py`, `demanda.py`, `eoq_rop.py`, `proveedor.py` y `ahorro.py`.
      - Un DataFrame vacío **con** las columnas requeridas sigue devolviendo
        una copia vacía con la columna `clase_abc`.
      - Motivo de la divergencia: `abc.py` se escribió antes de decidir la
        política estricta; se corrigió al terminar los 6 módulos del motor.

- [ ] **Extraer umbrales y parámetros a `parametros_configuracion`** (fase 4)
      - `abc.py`: `UMBRAL_CLASE_A`, `UMBRAL_CLASE_B`.
      - `xyz.py`: `UMBRAL_X`, `UMBRAL_Y`.
      - `demanda.py`: `VENTANA_DEFAULT`.
      - `eoq_rop.py`: `PERIODOS_POR_AÑO_DEFAULT`, `DIAS_POR_PERIODO_DEFAULT`,
        `MARGEN_SEGURIDAD_PCT_DEFAULT`.
      - `proveedor.py`: `UMBRAL_CONFIABLE`, `UMBRAL_RIESGOSO`,
        `PESO_CUMPLIMIENTO`, `PESO_CALIDAD`.
      - `ahorro.py`: `UMBRAL_AHORRO_PCT_DEFAULT`, `PERIODOS_POR_AÑO_DEFAULT`.
      - Deberán leerse desde Supabase en la fase 4.

- [ ] **Validar `float('inf')` en `ahorro.py`** (menor)
      - Actualmente `umbral_ahorro_pct = float('inf')` pasa la validación
        (solo se rechaza NaN y negativos).
      - Con `inf`, cualquier `ahorro_neto` queda "Sin oportunidad adicional".
      - Corregir añadiendo `math.isinf` a la validación.

- [ ] **Acoplamiento de unidades entre `eoq_rop.py` y `ahorro.py`**
      - Ambos usan `periodos_por_año`, pero se pasan por separado.
      - Si el llamador pasa valores distintos, hay inconsistencia.
      - Mitigar haciendo que `recomendador.py` pase el mismo valor a ambos.

## Notas de diseño

- **Tolerancias en comparaciones de frontera**: `abc.py`, `xyz.py`,
  `proveedor.py` y `ahorro.py` usan tolerancias para absorber errores de
  punto flotante en cortes exactos.

- **Año comercial de 360 días**: `eoq_rop.py` y `ahorro.py` usan 12
  periodos/año y 30 días/periodo por defecto.

- **Correcciones de notación en las fórmulas del MVP.md**: en `ahorro.py`
  se corrigieron tres errores de notación (falta `/100` en dos lugares,
  variable `EOQ_sin_descuento` indefinida).

- **Lectura B del criterio 6**: se interpreta "Oportunidad de ahorro por
  volumen" como evaluar si vale la pena subir el pedido al umbral de
  descuento.

## Casos conocidos y documentados

- **`descuento_pct = 0` en `ahorro.py`**: si un proveedor declara
  `cantidad_umbral_descuento` con `descuento_pct = 0`, el módulo sube el
  pedido al umbral sin obtener ahorro. El caso es raro en la práctica.

- **El prorrateo del costo extra hace el criterio más permisivo**:
  revisar las expectativas del seed para el criterio 6 en la fase de
  integración.

- **Ejemplos numéricos en los prompts deben verificarse con calculadora.**