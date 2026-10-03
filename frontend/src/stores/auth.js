import { defineStore } from 'pinia'
import { supabase } from '../services/supabase'

// Promesa de inicialización compartida: si `inicializar()` se llama dos veces
// (por ejemplo desde `main.js` y desde un guard del router a la vez), la
// segunda llamada espera a la primera en lugar de repetir el trabajo.
let inicializacionEnCurso = null

// Evita registrar más de una vez el listener de Supabase Auth.
let suscripcionRegistrada = false

// Los mensajes de error de Supabase Auth llegan en inglés; se traducen los
// casos conocidos y se deja el mensaje original como último recurso.
const ERRORES_AUTH_ES = [
  ['invalid login credentials', 'Email o contraseña incorrectos.'],
  ['email not confirmed', 'La cuenta todavía no está confirmada. Revisa tu correo.'],
  ['user already registered', 'Ya existe una cuenta registrada con ese email.'],
  ['already been registered', 'Ya existe una cuenta registrada con ese email.'],
  ['password should be at least', 'La contraseña debe tener al menos 6 caracteres.'],
  ['unable to validate email address', 'El email no tiene un formato válido.'],
  ['email rate limit exceeded', 'Demasiados intentos. Espera unos minutos y vuelve a probar.'],
  ['signups not allowed', 'El registro de usuarios está deshabilitado.'],
  ['signup is disabled', 'El registro de usuarios está deshabilitado.'],
  ['user not found', 'No existe una cuenta con ese email.'],
  ['auth session missing', 'No hay una sesión activa.'],
  ['failed to fetch', 'No se pudo conectar con el servidor. Revisa tu conexión.'],
]

/**
 * Traduce un error de Supabase Auth a un mensaje en español.
 * Si no se reconoce el error, devuelve el mensaje original.
 */
export function traducirErrorAuth(error) {
  if (!error) return 'Ocurrió un error inesperado.'
  const mensaje = error.message || String(error)
  const enMinusculas = mensaje.toLowerCase()
  const conocida = ERRORES_AUTH_ES.find(([clave]) => enMinusculas.includes(clave))
  return conocida ? conocida[1] : mensaje
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    session: null,
    isAdmin: false,
    cargando: true,
  }),

  getters: {
    estaAutenticado: (state) => !!state.user,
    listo: (state) => !state.cargando,
  },

  actions: {
    /**
     * Lee la sesión actual de Supabase, carga el usuario y verifica si es
     * admin. Es await-able e idempotente: dos llamadas concurrentes comparten
     * la misma promesa, así que la segunda espera a la primera.
     */
    inicializar() {
      if (!inicializacionEnCurso) {
        inicializacionEnCurso = this.inicializarSesion()
      }
      return inicializacionEnCurso
    },

    async inicializarSesion() {
      try {
        const { data, error } = await supabase.auth.getSession()
        if (error) throw error
        const sesion = data.session ?? null
        this.session = sesion
        this.user = sesion?.user ?? null
        await this.cargarAdmin()
      } catch {
        // Sin sesión recuperable: la app arranca como visitante.
        this.session = null
        this.user = null
        this.isAdmin = false
      } finally {
        this.escucharCambiosDeSesion()
        this.cargando = false
      }
    },

    /**
     * Se suscribe a los cambios de sesión (login, logout, refresh de token).
     * El callback sólo actualiza `user` y `session`: llamar a métodos de
     * Supabase con `await` dentro del callback puede producir un deadlock
     * (el cliente mantiene su lock interno mientras notifica), así que
     * `cargarAdmin()` se dispara aparte.
     */
    escucharCambiosDeSesion() {
      if (suscripcionRegistrada) return
      suscripcionRegistrada = true

      supabase.auth.onAuthStateChange((_evento, sesion) => {
        const idAnterior = this.user?.id ?? null
        const idNuevo = sesion?.user?.id ?? null

        this.session = sesion ?? null
        this.user = sesion?.user ?? null

        // Sólo se recalcula el rol cuando cambia el usuario (login o logout);
        // un refresh de token no vuelve a consultar la tabla `admins`.
        if (idNuevo !== idAnterior) {
          setTimeout(() => {
            this.cargarAdmin()
          }, 0)
        }
      })
    },

    /**
     * Inicia sesión con email y contraseña.
     * Devuelve `{ ok: true }` o `{ ok: false, error }`.
     */
    async login(email, password) {
      try {
        const { data, error } = await supabase.auth.signInWithPassword({
          email,
          password,
        })
        if (error) return { ok: false, error: traducirErrorAuth(error) }

        this.session = data.session ?? null
        this.user = data.user ?? null
        await this.cargarAdmin()
        return { ok: true }
      } catch (error) {
        return { ok: false, error: traducirErrorAuth(error) }
      }
    },

    /**
     * Registra un usuario nuevo. Con la confirmación por email desactivada,
     * Supabase devuelve la sesión en la misma respuesta, así que el usuario
     * queda logueado inmediatamente.
     * Devuelve `{ ok: true }` o `{ ok: false, error }`.
     */
    async signup(email, password) {
      try {
        const { data, error } = await supabase.auth.signUp({ email, password })
        if (error) return { ok: false, error: traducirErrorAuth(error) }

        this.session = data.session ?? null
        this.user = data.user ?? null
        await this.cargarAdmin()
        return { ok: true }
      } catch (error) {
        return { ok: false, error: traducirErrorAuth(error) }
      }
    },

    /** Cierra la sesión y limpia el estado local. */
    async logout() {
      try {
        await supabase.auth.signOut()
      } catch {
        // Aunque falle la revocación remota, se limpia el estado local.
      } finally {
        this.session = null
        this.user = null
        this.isAdmin = false
      }
    },

    /**
     * Consulta la tabla `admins` para saber si el usuario actual tiene rol de
     * administrador. Sin usuario, `isAdmin` queda en false.
     */
    async cargarAdmin() {
      if (!this.user) {
        this.isAdmin = false
        return false
      }

      try {
        const { data, error } = await supabase
          .from('admins')
          .select('user_id')
          .eq('user_id', this.user.id)
          .maybeSingle()
        if (error) throw error
        this.isAdmin = !!data
        return this.isAdmin
      } catch {
        this.isAdmin = false
        return false
      }
    },
  },
})

