<script setup>
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

async function cerrarSesion() {
  await authStore.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <header class="bg-white shadow-sm">
    <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
      <div class="flex items-center gap-6">
        <RouterLink to="/" class="text-xl font-semibold text-gray-800">
          Sistema de Optimización de Compras
        </RouterLink>

        <nav v-if="authStore.estaAutenticado" class="flex items-center gap-4 text-sm">
          <RouterLink to="/" class="text-gray-600 hover:text-gray-900">
            Inicio
          </RouterLink>
        </nav>
      </div>

      <div
        v-if="authStore.estaAutenticado"
        class="flex items-center gap-3 text-sm"
      >
        <span
          v-if="authStore.isAdmin"
          class="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800"
        >
          Admin
        </span>
        <span class="text-gray-600">{{ authStore.user?.email }}</span>
        <button
          type="button"
          class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          @click="cerrarSesion"
        >
          Cerrar sesión
        </button>
      </div>

      <div v-else class="flex items-center gap-4 text-sm">
        <RouterLink to="/login" class="text-gray-600 hover:text-gray-900">
          Iniciar sesión
        </RouterLink>
        <RouterLink
          to="/register"
          class="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          Registrarse
        </RouterLink>
      </div>
    </div>
  </header>
</template>
