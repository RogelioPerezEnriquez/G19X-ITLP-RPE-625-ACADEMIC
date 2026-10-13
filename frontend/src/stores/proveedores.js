import { defineStore } from 'pinia'
import { supabase } from '../services/supabase'

// El score y el estado no son columnas de `proveedores`: se calculan acá
// replicando la fórmula del criterio 5 del MVP.md, cuya fuente única de verdad
// es `backend/src/motor/proveedor.py`:
//
//   score = cumplimiento_entrega_pct * 0.6 + (100 - tasa_defectos_pct) * 0.4
//
// Los cortes sobre el score definen el estado (corte confiable INCLUSIVO,
// corte riesgoso EXCLUSIVO: un score igual al umbral de riesgo es "Aceptable"):
//   "Confiable"              si score >= umbralConfiable
//   "Riesgoso"               si score <  umbralRiesgoso
//   "Aceptable con reservas" en cualquier otro caso
//
// Los umbrales se leen de `parametros_configuracion` en cada `listar()` para
// respetar el criterio 7 (configurabilidad): cambiarlos en la pantalla de
// configuración se refleja acá sin tocar código. Los valores 80 y 60 de abajo
// son solo el FALLBACK, usado si la consulta falla, si falta un parámetro o si
// su valor no es un número válido.
export const PESO_CUMPLIMIENTO = 0.6
export const PESO_CALIDAD = 0.4
export const UMBRAL_CONFIABLE = 80
export const UMBRAL_RIESGOSO = 60

export const ORDEN_ESTADO = ['Confiable', 'Aceptable con reservas', 'Riesgoso']

// Tolerancia al comparar el score con los umbrales, replicada de
// `TOLERANCIA_SCORE` en `backend/src/motor/proveedor.py`. Absorbe el ruido de
// punto flotante: un score matemático de 60 puede representarse como
// 59.99999999999999 (p. ej. cumplimiento 96 con defectos 94) y sin tolerancia
// quedaría "Riesgoso" en lugar de "Aceptable con reservas".
const TOLERANCIA_SCORE = 1e-9

export function calcularScore(cumplimientoEntregaPct, tasaDefectosPct) {
  const calidad = 100 - Number(tasaDefectosPct ?? 0)
  return (
    Number(cumplimientoEntregaPct ?? 0) * PESO_CUMPLIMIENTO +
    calidad * PESO_CALIDAD
  )
}

// Regla de clasificación (replicada de `backend/src/motor/proveedor.py`):
//   score >= umbralConfiable  -> "Confiable"              (corte INCLUSIVO)
//   score <  umbralRiesgoso   -> "Riesgoso"               (corte EXCLUSIVO:
//   cualquier otro caso       -> "Aceptable con reservas"  un score igual al
//                                                          umbral de riesgo
//                                                          NO es Riesgoso)
// Si no se pasan umbrales, se usan los defaults (fallback, ver arriba).
export function calcularEstado(
  score,
  umbralConfiable = UMBRAL_CONFIABLE,
  umbralRiesgoso = UMBRAL_RIESGOSO
) {
  if (score >= umbralConfiable - TOLERANCIA_SCORE) return 'Confiable'
  if (score < umbralRiesgoso - TOLERANCIA_SCORE) return 'Riesgoso'
  return 'Aceptable con reservas'
}

// Agrega a la fila de `proveedores` el score y el estado calculados con los
// umbrales vigentes (leídos de `parametros_configuracion` o los defaults).
function enriquecer(
  fila,
  umbrales = { confiable: UMBRAL_CONFIABLE, riesgoso: UMBRAL_RIESGOSO }
) {
  const score = calcularScore(
    fila.cumplimiento_entrega_pct,
    fila.tasa_defectos_pct
  )
  return {
    ...fila,
    score,
    estado: calcularEstado(score, umbrales.confiable, umbrales.riesgoso),
  }
}

// Score descendente; desempate por nombre ascendente.
function compararProveedores(a, b) {
  const porScore = Number(b.score ?? 0) - Number(a.score ?? 0)
  if (porScore !== 0) return porScore
  return String(a.nombre ?? '').localeCompare(String(b.nombre ?? ''), 'es')
}

// Parámetros de `parametros_configuracion` que definen los cortes del score.
const PARAM_CONFIABLE = 'score_proveedor_confiable'
const PARAM_RIESGOSO = 'score_proveedor_riesgoso'

// Un valor configurable es válido solo si existe y es un número finito.
// `null`/`undefined`/'' se rechazan explícitamente para no convertirlos
// silenciosamente en 0 (Number(null) === 0).
function esUmbralValido(valor) {
  if (valor === null || valor === undefined || valor === '') return false
  return Number.isFinite(Number(valor))
}

/**
 * Lee los umbrales de score desde `parametros_configuracion` (criterio 7,
 * configurabilidad). Los defaults (80 y 60) se inicializan ANTES de consultar
 * y son el fallback: si la consulta falla, si falta un parámetro o si su valor
 * no es un número válido, ese umbral conserva su default y se continúa con el
 * resto. Nunca lanza: el listado de proveedores no debe caerse por la tabla
 * de configuración.
 */
async function cargarUmbrales() {
  const umbrales = { confiable: UMBRAL_CONFIABLE, riesgoso: UMBRAL_RIESGOSO }

  try {
    const { data, error } = await supabase
      .from('parametros_configuracion')
      .select('nombre_parametro, valor')
      .in('nombre_parametro', [PARAM_CONFIABLE, PARAM_RIESGOSO])

    if (error) return umbrales

    for (const fila of data ?? []) {
      if (fila.nombre_parametro === PARAM_CONFIABLE && esUmbralValido(fila.valor)) {
        umbrales.confiable = Number(fila.valor)
      }
      if (fila.nombre_parametro === PARAM_RIESGOSO && esUmbralValido(fila.valor)) {
        umbrales.riesgoso = Number(fila.valor)
      }
    }
  } catch {
    // Error inesperado (p. ej. red): se conservan los defaults.
  }

  return umbrales
}

// Los mensajes de Supabase llegan en inglés: se traducen los casos conocidos y
// se deja el mensaje original como último recurso.
function mensajeDeError(error) {
  if (!error) return 'Ocurrió un error inesperado al cargar los proveedores.'
  const mensaje = error.message || String(error)
  const enMinusculas = mensaje.toLowerCase()
  if (enMinusculas.includes('failed to fetch') || enMinusculas.includes('network')) {
    return 'No se pudo conectar con el servidor. Revisa tu conexión.'
  }
  return mensaje
}

export const useProveedoresStore = defineStore('proveedores', {
  state: () => ({
    items: [],
    cargando: false,
    error: null,
  }),

  getters: {
    porEstado: (state) => (estado) =>
      state.items.filter((item) => item.estado === estado),
  },

  actions: {
    /**
     * Consulta `proveedores` y los umbrales de `parametros_configuracion`
     * (criterio 7), calcula el score y el estado de cada fila con esos
     * umbrales y deja `items` ordenado por score descendente (desempate por
     * nombre ascendente). Se llama en cada ingreso a la vista, así que un
     * cambio de parámetros se refleja al volver a entrar. Devuelve el arreglo
     * resultante (queda vacío si hubo error).
     */
    async listar() {
      this.cargando = true
      this.error = null

      try {
        // Las dos consultas son independientes: se disparan en paralelo. Si la
        // de parámetros falla, `cargarUmbrales` resuelve con los defaults.
        const [umbrales, { data, error }] = await Promise.all([
          cargarUmbrales(),
          supabase
            .from('proveedores')
            .select('id, nombre, cumplimiento_entrega_pct, tasa_defectos_pct'),
        ])

        if (error) throw error

        this.items = (data ?? [])
          .map((fila) => enriquecer(fila, umbrales))
          .sort(compararProveedores)
        return this.items
      } catch (error) {
        this.error = mensajeDeError(error)
        this.items = []
        return []
      } finally {
        this.cargando = false
      }
    },
  },
})
