<script setup>
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

// Vista temporal de home.
// Será reemplazada por la cola de recomendaciones en la fase 6.2.
</script>

<template>
  <div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-lg font-medium text-gray-900 mb-2">
      Bienvenido, {{ authStore.user?.email }}
    </h2>
    <span
      v-if="authStore.isAdmin"
      class="inline-block rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-800 mb-3"
    >
      Administrador
    </span>
    <p class="text-gray-600">
      Sistema en construcción. Las vistas se agregarán en las
      próximas fases.
    </p>
  </div>
</template>