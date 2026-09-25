# Pendientes técnicos

Este archivo registra decisiones que quedan abiertas, deuda técnica, y
aspectos a revisar antes de cerrar el MVP.

## Deuda técnica

- [ ] **Unificar validación de columnas entre módulos del motor**
      - `abc.py`: permisivo con DataFrames vacíos sin columnas (devuelve vacío).
      - `xyz.py`, `demanda.py` y siguientes: estricto (lanza `ValueError` siempre).
      - Motivo de la divergencia: `abc.py` se escribió antes de decidir la
        política estricta.
      - Revisar al terminar los 6 módulos del motor.

- [ ] **Extraer umbrales y parámetros a `parametros_configuracion`** (fase 4)
      - `abc.py`: `UMBRAL_CLASE_A`, `UMBRAL_CLASE_B`.
      - `xyz.py`: `UMBRAL_X`, `UMBRAL_Y`.
      - `demanda.py`: `VENTANA_DEFAULT`.
      - Deberán leerse desde Supabase en la fase 4.

## Notas

- Los ejemplos numéricos en los prompts deben verificarse con calculadora.
  En `xyz.py` hubo un error en los CV del ejemplo (los valores correctos
  con ddof=1 son distintos a los que puse originalmente).