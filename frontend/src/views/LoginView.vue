<script setup>
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const error = ref('')
const enviando = ref(false)

async function manejarEnvio() {
  error.value = ''
  enviando.value = true
  const resultado = await authStore.login(email.value, password.value)
  enviando.value = false

  if (!resultado.ok) {
    error.value = resultado.error
    return
  }

  const destino =
    typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  await router.push(destino)
}
</script>

<template>
  <div class="flex justify-center">
    <div class="w-full max-w-md bg-white rounded-lg shadow p-6">
      <h2 class="text-lg font-medium text-gray-900 mb-4">Iniciar sesión</h2>

      <form class="space-y-4" @submit.prevent="manejarEnvio">
        <div>
          <label for="email" class="block text-sm font-medium text-gray-700 mb-1">
            Email
          </label>
          <input
            id="email"
            v-model="email"
            type="email"
            required
            autocomplete="email"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div>
          <label for="password" class="block text-sm font-medium text-gray-700 mb-1">
            Contraseña
          </label>
          <input
            id="password"
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>

        <button
          type="submit"
          :disabled="enviando"
          class="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {{ enviando ? 'Iniciando sesión...' : 'Iniciar sesión' }}
        </button>
      </form>

      <p class="mt-4 text-center text-sm text-gray-600">
        ¿No tienes cuenta?
        <RouterLink to="/register" class="text-blue-600 hover:underline">
          Regístrate
        </RouterLink>
      </p>
    </div>
  </div>
</template>
