import { defineStore } from 'pinia'
import { supabase } from '../services/supabase'

// Los mensajes de Supabase llegan en inglés: se traducen los casos conocidos y
// se deja el mensaje original como último recurso.
function mensajeDeError(error, contexto) {
  if (!error) return `Ocurrió un error inesperado al ${contexto}.`
  const mensaje = error.message || String(error)
  const enMinusculas = mensaje.toLowerCase()
  if (enMinusculas.includes('failed to fetch') || enMinusculas.includes('network')) {
    return 'No se pudo conectar con el servidor. Revisa tu conexión.'
  }
  if (enMinusculas.includes('row-level security')) {
    return 'No tienes permisos para modificar los parámetros. Se requiere rol de administrador.'
  }
  return mensaje
}

export const useConfiguracionStore = defineStore('configuracion', {
  state: () => ({
    // Cada parámetro: { nombre_parametro, valor, descripcion, valorOriginal }.
    // `valorOriginal` es la copia del último valor persistido, usada para
    // detectar cambios y para el botón "Cancelar".
    parametros: [],
    cargando: false,
    guardando: false,
    error: null,
    exito: null,
  }),

  getters: {
    /** True si algún valor difiere del último valor persistido. */
    hayCambios: (state) =>
      state.parametros.some(
        (p) => Number(p.valor) !== Number(p.valorOriginal)
      ),

    /** Subconjunto de parámetros cuyo valor difiere de `valorOriginal`. */
    modificados: (state) =>
      state.parametros.filter(
        (p) => Number(p.valor) !== Number(p.valorOriginal)
      ),
  },

  actions: {
    /**
     * Carga todos los parámetros de `parametros_configuracion`, ordenados por
     * `nombre_parametro` ascendente. Guarda una copia del valor persistido en
     * `valorOriginal` para poder detectar cambios.
     */
    async listar() {
      this.cargando = true
      this.error = null
      this.exito = null

      try {
        const { data, error } = await supabase
          .from('parametros_configuracion')
          .select('nombre_parametro, valor, descripcion')
          .order('nombre_parametro', { ascending: true })

        if (error) throw error

        this.parametros = (data ?? []).map((fila) => ({
          nombre_parametro: fila.nombre_parametro,
          valor: Number(fila.valor),
          descripcion: fila.descripcion ?? '',
          valorOriginal: Number(fila.valor),
        }))
        return this.parametros
      } catch (error) {
        this.error = mensajeDeError(error, 'cargar los parámetros')
        this.parametros = []
        return []
      } finally {
        this.cargando = false
      }
    },

    /**
     * Persiste solo los parámetros modificados, con un UPDATE por cada uno.
     * Si todo va bien, actualiza `valorOriginal` con el nuevo valor y setea
     * `exito`. Si algo falla, setea `error` indicando qué parámetro falló.
     * Devuelve true/false según el resultado.
     */
    async actualizarTodos() {
      const modificados = this.modificados
      if (modificados.length === 0) return true

      this.guardando = true
      this.error = null
      this.exito = null

      try {
        for (const parametro of modificados) {
          const { error } = await supabase
            .from('parametros_configuracion')
            .update({ valor: Number(parametro.valor) })
            .eq('nombre_parametro', parametro.nombre_parametro)

          if (error) {
            throw Object.assign(error, {
              _parametro: parametro.nombre_parametro,
            })
          }
        }

        for (const parametro of modificados) {
          parametro.valorOriginal = Number(parametro.valor)
        }
        this.exito = 'Parámetros actualizados correctamente.'
        return true
      } catch (error) {
        const detalle = error?._parametro
          ? ` No se pudo guardar "${error._parametro}".`
          : ''
        this.error = `${mensajeDeError(error, 'guardar los parámetros')}${detalle}`
        return false
      } finally {
        this.guardando = false
      }
    },

    /**
     * Actualiza un solo parámetro por nombre. Útil para ajustes puntuales
     * sin pasar por el formulario completo.
     * Devuelve true/false según el resultado.
     */
    async actualizarUno(nombre, valor) {
      const parametro = this.parametros.find(
        (p) => p.nombre_parametro === nombre
      )
      const valorNumerico = Number(valor)
      if (!parametro || !Number.isFinite(valorNumerico)) {
        this.error = 'El parámetro o el valor indicado no son válidos.'
        return false
      }

      this.guardando = true
      this.error = null
      this.exito = null

      try {
        const { error } = await supabase
          .from('parametros_configuracion')
          .update({ valor: valorNumerico })
          .eq('nombre_parametro', nombre)

        if (error) throw error

        parametro.valor = valorNumerico
        parametro.valorOriginal = valorNumerico
        this.exito = `Parámetro "${nombre}" actualizado correctamente.`
        return true
      } catch (error) {
        this.error = mensajeDeError(error, 'guardar el parámetro')
        return false
      } finally {
        this.guardando = false
      }
    },

    /** Restaura los valores editados a su último valor persistido. */
    descartarCambios() {
      for (const parametro of this.parametros) {
        parametro.valor = parametro.valorOriginal
      }
      this.error = null
      this.exito = null
    },
  },
})
