import { defineStore } from 'pinia'

// URL base del backend FastAPI (se define en el `.env` de la raíz).
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// El mensaje de bienvenida es solo de UI: no se agrega al `historial` que se
// envía al backend, porque el agente no lo necesita para contextualizar.
const MENSAJE_BIENVENIDA =
  '¡Hola! Soy tu asistente de compras. Puedes preguntarme por las recomendaciones, las prioridades ABC/XYZ o el detalle de un producto.'

/**
 * Traduce un error de red o del servidor a un mensaje claro en español.
 * `fetch` lanza `TypeError: Failed to fetch` cuando el servidor no responde
 * (caído o sin conexión), y no lanza excepción ante respuestas 4xx/5xx.
 */
function mensajeDeError(error) {
  if (!error) return 'Ocurrió un error inesperado al consultar al agente.'
  const mensaje = error.message || String(error)
  const enMinusculas = mensaje.toLowerCase()
  if (enMinusculas.includes('failed to fetch') || enMinusculas.includes('network')) {
    return 'No se pudo conectar con el servidor del agente. Verifica que esté en ejecución.'
  }
  return mensaje
}

function ahora() {
  return new Date().toISOString()
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    // Mensajes visibles en la vista; incluyen `timestamp` para ordenar/mostrar.
    mensajes: [],
    // Historial que se envía al backend: solo `role` y `content`.
    historial: [],
    cargando: false,
    error: null,
  }),

  getters: {
    hayMensajes: (state) => state.mensajes.length > 0,
  },

  actions: {
    /**
     * Agrega el mensaje inicial del asistente si el chat está vacío.
     * Idempotente: llamarla con mensajes existentes no hace nada.
     */
    inicializar() {
      if (this.mensajes.length > 0) return
      this.mensajes.push({
        role: 'assistant',
        content: MENSAJE_BIENVENIDA,
        timestamp: ahora(),
      })
    },

    /**
     * Envía la pregunta al agente (`POST /agente/preguntar`) con el historial
     * acumulado y agrega la respuesta al chat. Ante un fallo, registra el
     * error y también lo muestra como mensaje del asistente para no dejar la
     * conversación "colgada".
     */
    async enviar(pregunta) {
      const texto = (pregunta ?? '').trim()
      if (!texto || this.cargando) return

      this.error = null
      this.mensajes.push({ role: 'user', content: texto, timestamp: ahora() })
      this.historial.push({ role: 'user', content: texto })
      this.cargando = true

      try {
        const respuesta = await fetch(`${API_URL}/agente/preguntar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pregunta: texto, historial: this.historial }),
        })

        if (!respuesta.ok) {
          throw new Error(`El agente respondió con un error (código ${respuesta.status}).`)
        }

        const datos = await respuesta.json()
        const contenido =
          datos?.respuesta ?? 'El agente no devolvió una respuesta.'

        this.mensajes.push({
          role: 'assistant',
          content: contenido,
          timestamp: ahora(),
        })

        // Se adopta el historial devuelto por el backend (puede haberlo
        // normalizado o enriquecido); si no lo devuelve, se agrega la
        // respuesta al historial local.
        if (Array.isArray(datos?.historial)) {
          this.historial = datos.historial
            .filter((m) => m && m.role && m.content)
            .map((m) => ({ role: m.role, content: m.content }))
        } else {
          this.historial.push({ role: 'assistant', content: contenido })
        }
      } catch (error) {
        const mensaje = mensajeDeError(error)
        this.error = mensaje
        this.mensajes.push({
          role: 'assistant',
          content: `No pude procesar tu consulta. ${mensaje}`,
          timestamp: ahora(),
        })
      } finally {
        this.cargando = false
      }
    },

    /**
     * Vacía el chat: mensajes, historial y error. Para volver a mostrar el
     * mensaje de bienvenida hay que llamar a `inicializar()` después.
     */
    limpiar() {
      this.mensajes = []
      this.historial = []
      this.error = null
    },
  },
})
