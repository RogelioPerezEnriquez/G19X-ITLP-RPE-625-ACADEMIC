# Pendientes técnicos

Este archivo registra decisiones que quedan abiertas, deuda técnica, y
aspectos a revisar antes de cerrar el MVP.

## Deuda técnica

- [ ] **Unificar validación de columnas entre módulos del motor**
      - `abc.py`: permisivo con DataFrames vacíos sin columnas (devuelve vacío).
      - `xyz.py` y siguientes: estricto (lanza `ValueError` siempre).
      - Revisar al terminar los 6 módulos del motor.

- [ ] **Extraer umbrales a `parametros_configuracion`** (fase 4)
      - `abc.py` tiene `UMBRAL_CLASE_A` y `UMBRAL_CLASE_B` hardcodeados.
      - `xyz.py` tiene `UMBRAL_X` y `UMBRAL_Y` hardcodeados.
      - Deberán leerse desde Supabase en la fase 4.

## Notas

- Los ejemplos numéricos en los prompts deben verificarse con calculadora.
  En `xyz.py` hubo un error en los CV del ejemplo (los valores correctos
  con ddof=1 son distintos a los que puse originalmente).