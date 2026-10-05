import { defineStore } from 'pinia'
import { supabase } from '../services/supabase'

// El score y el estado no son columnas de `proveedores`: se calculan acá
// replicando la fórmula del criterio 5 del MVP.md, cuya fuente única de verdad
// es `backend/src/motor/proveedor.py`:
//
//   score = cumplimiento_entrega_pct * 0.6 + (100 - tasa_defectos_pct) * 0.4
//
// Los cortes sobre el score definen el estado:
//   "Confiable"              si score >= 80
//   "Aceptable con reservas" si 60 <= score < 80
//   "Riesgoso"               si score < 60
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

export function calcularEstado(score) {
  if (score >= UMBRAL_CONFIABLE - TOLERANCIA_SCORE) return 'Confiable'
  if (score < UMBRAL_RIESGOSO - TOLERANCIA_SCORE) return 'Riesgoso'
  return 'Aceptable con reservas'
}

// Agrega a la fila de `proveedores` el score y el estado calculados.
function enriquecer(fila) {
  const score = calcularScore(
    fila.cumplimiento_entrega_pct,
    fila.tasa_defectos_pct
  )
  return {
    ...fila,
    score,
    estado: calcularEstado(score),
  }
}

// Score descendente; desempate por nombre ascendente.
function compararProveedores(a, b) {
  const porScore = Number(b.score ?? 0) - Number(a.score ?? 0)
  if (porScore !== 0) return porScore
  return String(a.nombre ?? '').localeCompare(String(b.nombre ?? ''), 'es')
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
     * Consulta `proveedores`, calcula el score y el estado de cada fila y deja
     * `items` ordenado por score descendente (desempate por nombre ascendente).
     * Devuelve el arreglo resultante (queda vacío si hubo error).
     */
    async listar() {
      this.cargando = true
      this.error = null

      try {
        const { data, error } = await supabase
          .from('proveedores')
          .select('id, nombre, cumplimiento_entrega_pct, tasa_defectos_pct')

        if (error) throw error

        this.items = (data ?? []).map(enriquecer).sort(compararProveedores)
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
