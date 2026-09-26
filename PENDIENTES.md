## Deuda técnica

- [ ] **Unificar validación de columnas entre módulos del motor**
      - `abc.py`: permisivo con DataFrames vacíos sin columnas (devuelve vacío).
      - `xyz.py`, `demanda.py`, `eoq_rop.py` y siguientes: estricto (lanza
        `ValueError` siempre).
      - Motivo de la divergencia: `abc.py` se escribió antes de decidir la
        política estricta.
      - Revisar al terminar los 6 módulos del motor.

- [ ] **Extraer umbrales y parámetros a `parametros_configuracion`** (fase 4)
      - `abc.py`: `UMBRAL_CLASE_A`, `UMBRAL_CLASE_B`.
      - `xyz.py`: `UMBRAL_X`, `UMBRAL_Y`.
      - `demanda.py`: `VENTANA_DEFAULT`.
      - `eoq_rop.py`: `PERIODOS_POR_AÑO_DEFAULT`, `DIAS_POR_PERIODO_DEFAULT`,
        `MARGEN_SEGURIDAD_PCT_DEFAULT`.
      - Deberán leerse desde Supabase en la fase 4.

## Notas de diseño

- **Tolerancias en comparaciones de frontera**: `abc.py`, `xyz.py` y
  `proveedor.py` usan una tolerancia (`TOLERANCIA_PCT`, `TOLERANCIA_CV`,
  `TOLERANCIA_SCORE`) para absorber errores de punto flotante en cortes
  exactos. Ejemplo: un score matemático de 60 puede representarse como
  59.99999999999999. La tolerancia garantiza que ese caso se clasifique
  correctamente como "Aceptable con reservas" y no como "Riesgoso".

- **Año comercial de 360 días**: `eoq_rop.py` usa 12 periodos/año y 30
  días/periodo por defecto, lo que implica un año de 360 días. Coherente
  con la convención de "año comercial" y documentado en el docstring.
  No afecta al MVP.

- **Ejemplos numéricos en los prompts deben verificarse con calculadora.**
  Ya hubo un error en `xyz.py` (los CV del ejemplo) que se corrigió en el
  módulo.