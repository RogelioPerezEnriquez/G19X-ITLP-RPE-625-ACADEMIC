import { defineStore } from 'pinia'
import { supabase } from '../services/supabase'

// Jerarquía de negocio de la urgencia, de mayor a menor prioridad. El orden de
// este arreglo define tanto el ordenamiento de la cola como las etiquetas del
// filtro.
export const ORDEN_URGENCIA = ['Crítico', 'Atención', 'Sin riesgo']

// La urgencia no es una columna de `recomendaciones`: se deriva comparando el
// `stock_actual` del producto con el `stock_seguridad` y el `punto_reorden` de
// la recomendación. Los cortes son los mismos que usa el motor en el backend.
export function calcularUrgencia(stockActual, stockSeguridad, puntoReorden) {
  if (stockActual <= stockSeguridad) return 'Crítico'
  if (stockActual <= puntoReorden) return 'Atención'
  return 'Sin riesgo'
}

// PostgREST devuelve las relaciones embebidas como objeto (relación N:1); ante
// una respuesta inesperada se acepta también un arreglo.
function primerElemento(valor) {
  if (Array.isArray(valor)) return valor[0] ?? null
  return valor ?? null
}

// Combina la fila de `recomendaciones` con los datos de `productos` y
// `proveedores` y agrega la urgencia calculada en el frontend.
function enriquecer(fila) {
  const producto = primerElemento(fila.productos)
  const proveedor = primerElemento(fila.proveedores)

  const stockActual = Number(producto?.stock_actual ?? 0)
  const stockSeguridad = Number(fila.stock_seguridad ?? 0)
  const puntoReorden = Number(fila.punto_reorden ?? 0)

  return {
    ...fila,
    producto_nombre: producto?.nombre ?? 'Producto sin nombre',
    proveedor_nombre: proveedor?.nombre ?? 'Proveedor sin nombre',
    stock_actual: stockActual,
    urgencia: calcularUrgencia(stockActual, stockSeguridad, puntoReorden),
  }
}

// Urgencia, luego ahorro neto descendente y, como desempate final,
// `producto_id` ascendente.
function compararRecomendaciones(a, b) {
  const porUrgencia =
    ORDEN_URGENCIA.indexOf(a.urgencia) - ORDEN_URGENCIA.indexOf(b.urgencia)
  if (porUrgencia !== 0) return porUrgencia

  const porAhorro =
    Number(b.ahorro_neto_estimado ?? 0) - Number(a.ahorro_neto_estimado ?? 0)
  if (porAhorro !== 0) return porAhorro

  return String(a.producto_id ?? '').localeCompare(String(b.producto_id ?? ''))
}

// Los mensajes de Supabase llegan en inglés: se traducen los casos conocidos y
// se deja el mensaje original como último recurso.
function mensajeDeError(error) {
  if (!error) return 'Ocurrió un error inesperado al cargar las recomendaciones.'
  const mensaje = error.message || String(error)
  const enMinusculas = mensaje.toLowerCase()
  if (enMinusculas.includes('failed to fetch') || enMinusculas.includes('network')) {
    return 'No se pudo conectar con el servidor. Revisa tu conexión.'
  }
  return mensaje
}

// SELECT único del panel de explicabilidad: la recomendación con su producto,
// su proveedor y sus evaluaciones de criterios embebidas. `productos` va con
// `!inner` porque, sin él, PostgREST no filtra las filas padre por columnas
// del recurso embebido: devolvería todas las recomendaciones (con
// `productos: null` en las que no coinciden) y `limit(1)` traería la más
// reciente de cualquier producto.
const SELECT_DETALLE = `
  *,
  productos!inner(nombre, categoria, stock_actual),
  proveedores(nombre, cumplimiento_entrega_pct, tasa_defectos_pct),
  evaluaciones_criterios(criterio, estado, valor_numerico)
`

// La ruta `/recomendaciones/:productoId` puede llevar el nombre del producto o
// su UUID (la tarjeta de la cola navega con `producto_id`). Este patrón
// permite elegir por cuál columna filtrar.
const PATRON_UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// Normaliza la fila cruda: los embeds N:1 llegan como objeto (o arreglo ante
// una respuesta inesperada) y las evaluaciones siempre como arreglo.
function normalizarDetalle(fila) {
  return {
    ...fila,
    producto: primerElemento(fila.productos),
    proveedor: primerElemento(fila.proveedores),
    evaluaciones: Array.isArray(fila.evaluaciones_criterios)
      ? fila.evaluaciones_criterios
      : [],
  }
}

export const useRecomendacionesStore = defineStore('recomendaciones', {
  state: () => ({
    items: [],
    detalleActual: null,
    cargando: false,
    error: null,
  }),

  getters: {
    porUrgencia: (state) => (urgencia) =>
      state.items.filter((item) => item.urgencia === urgencia),
  },

  actions: {
    /**
     * Consulta `recomendaciones` con sus relaciones de `productos` y
     * `proveedores`, calcula la urgencia y deja `items` ordenado. Acepta
     * `filtro.urgencia` para quedarse con una sola urgencia.
     * Devuelve el arreglo resultante (queda vacío si hubo error).
     */
    async listar(filtro = {}) {
      this.cargando = true
      this.error = null

      try {
        const { data, error } = await supabase
          .from('recomendaciones')
          .select('*, productos(nombre, stock_actual), proveedores(nombre)')

        if (error) throw error

        let items = (data ?? []).map(enriquecer).sort(compararRecomendaciones)

        if (filtro.urgencia) {
          items = items.filter((item) => item.urgencia === filtro.urgencia)
        }

        this.items = items
        return this.items
      } catch (error) {
        this.error = mensajeDeError(error)
        this.items = []
        return []
      } finally {
        this.cargando = false
      }
    },

    /**
     * Trae la recomendación más reciente de un producto con su producto, su
     * proveedor y sus evaluaciones de criterios en UN solo SELECT anidado.
     *
     * `productoId` es el parámetro de la ruta: puede ser el nombre del
     * producto o su UUID (la tarjeta de la cola navega con `producto_id`), y
     * se elige la columna de filtro según el formato del valor.
     *
     * Devuelve el objeto completo normalizado o `null` si no existe (también
     * ante error, caso en el que `error` queda con el mensaje). El resultado
     * queda además en `detalleActual` para reutilizarlo.
     */
    async detalle(productoId) {
      this.cargando = true
      this.error = null
      this.detalleActual = null

      const columnaFiltro = PATRON_UUID.test(String(productoId))
        ? 'producto_id'
        : 'productos.nombre'

      try {
        let { data, error } = await supabase
          .from('recomendaciones')
          .select(SELECT_DETALLE)
          .eq(columnaFiltro, productoId)
          .order('fecha_generacion', { ascending: false })
          .limit(1)
          .maybeSingle()

        if (error) {
          // Respaldo: si `maybeSingle()` falla, se reintenta con `limit(1)`
          // y se toma la primera fila.
          const respaldo = await supabase
            .from('recomendaciones')
            .select(SELECT_DETALLE)
            .eq(columnaFiltro, productoId)
            .order('fecha_generacion', { ascending: false })
            .limit(1)

          if (respaldo.error) throw respaldo.error
          data = respaldo.data?.[0] ?? null
        }

        this.detalleActual = data ? normalizarDetalle(data) : null
        return this.detalleActual
      } catch (error) {
        this.error = mensajeDeError(error)
        this.detalleActual = null
        return null
      } finally {
        this.cargando = false
      }
    },
  },
})
