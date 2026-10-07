import { defineStore } from 'pinia'
import { supabase } from '../services/supabase'
import { calcularUrgencia } from './recomendaciones'

// PostgREST devuelve las relaciones embebidas como objeto (relación N:1); ante
// una respuesta inesperada se acepta también un arreglo.
function primerElemento(valor) {
  if (Array.isArray(valor)) return valor[0] ?? null
  return valor ?? null
}

// Los mensajes de Supabase llegan en inglés: se traducen los casos conocidos y
// se deja el mensaje original como último recurso.
function mensajeDeError(error) {
  if (!error) return 'Ocurrió un error inesperado al calcular los KPIs.'
  const mensaje = error.message || String(error)
  const enMinusculas = mensaje.toLowerCase()
  if (enMinusculas.includes('failed to fetch') || enMinusculas.includes('network')) {
    return 'No se pudo conectar con el servidor. Revisa tu conexión.'
  }
  return mensaje
}

// Estado inicial de las métricas, con todas las claves presentes para que la
// vista no tenga que manejar propiedades faltantes.
function metricasVacias() {
  return {
    total_recomendaciones: 0,
    productos_unicos: 0,
    con_ahorro_detectado: 0,
    suma_ahorro_neto: 0,
    por_urgencia: { 'Crítico': 0, 'Atención': 0, 'Sin riesgo': 0 },
    por_clase_abc: { A: 0, B: 0, C: 0 },
    por_clase_xyz: { X: 0, Y: 0, Z: 0 },
    por_combinacion_abc_xyz: {
      AX: 0, AY: 0, AZ: 0,
      BX: 0, BY: 0, BZ: 0,
      CX: 0, CY: 0, CZ: 0,
    },
  }
}

export const useKpisStore = defineStore('kpis', {
  state: () => ({
    metricas: metricasVacias(),
    cargando: false,
    error: null,
  }),

  actions: {
    /**
     * Consulta `recomendaciones` con su relación de `productos` (para obtener
     * `stock_actual`), calcula la urgencia de cada fila y agrega todas las
     * métricas del panel en `metricas`. Devuelve el objeto de métricas
     * (queda en ceros si hubo error).
     */
    async calcular() {
      this.cargando = true
      this.error = null

      try {
        const { data, error } = await supabase
          .from('recomendaciones')
          .select('*, productos(nombre, stock_actual)')

        if (error) throw error

        const metricas = metricasVacias()
        const productosIds = new Set()

        for (const fila of data ?? []) {
          const producto = primerElemento(fila.productos)

          const stockActual = Number(producto?.stock_actual ?? 0)
          const stockSeguridad = Number(fila.stock_seguridad ?? 0)
          const puntoReorden = Number(fila.punto_reorden ?? 0)

          const urgencia = calcularUrgencia(stockActual, stockSeguridad, puntoReorden)
          if (urgencia in metricas.por_urgencia) {
            metricas.por_urgencia[urgencia] += 1
          }

          const abc = String(fila.clase_abc ?? '').toUpperCase()
          if (abc in metricas.por_clase_abc) {
            metricas.por_clase_abc[abc] += 1
          }

          const xyz = String(fila.clase_xyz ?? '').toUpperCase()
          if (xyz in metricas.por_clase_xyz) {
            metricas.por_clase_xyz[xyz] += 1
          }

          const combinacion = `${abc}${xyz}`
          if (combinacion in metricas.por_combinacion_abc_xyz) {
            metricas.por_combinacion_abc_xyz[combinacion] += 1
          }

          const ahorro = Number(fila.ahorro_neto_estimado ?? 0)
          if (Number.isFinite(ahorro)) {
            metricas.suma_ahorro_neto += ahorro
            // Aproximación del criterio 6: hay ahorro detectado si el ahorro
            // neto estimado es estrictamente positivo.
            if (ahorro > 0) {
              metricas.con_ahorro_detectado += 1
            }
          }

          if (fila.producto_id) {
            productosIds.add(fila.producto_id)
          }

          metricas.total_recomendaciones += 1
        }

        metricas.productos_unicos = productosIds.size

        this.metricas = metricas
        return this.metricas
      } catch (error) {
        this.error = mensajeDeError(error)
        this.metricas = metricasVacias()
        return this.metricas
      } finally {
        this.cargando = false
      }
    },
  },
})
