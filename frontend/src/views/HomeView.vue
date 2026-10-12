<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

// Accesos rápidos a las vistas principales. "Configuración" sólo aplica a
// administradores (la ruta además está protegida con `requiresAdmin`).
const ACCESOS = [
  { etiqueta: 'Recomendaciones', to: '/recomendaciones' },
  { etiqueta: 'Proveedores', to: '/proveedores' },
  { etiqueta: 'Chat', to: '/chat' },
  { etiqueta: 'KPIs', to: '/kpis' },
  { etiqueta: 'Configuración', to: '/configuracion', soloAdmin: true },
]

const accesosVisibles = computed(() =>
  ACCESOS.filter((acceso) => !acceso.soloAdmin || authStore.isAdmin)
)
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

    <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <RouterLink
        v-for="acceso in accesosVisibles"
        :key="acceso.to"
        :to="acceso.to"
        class="rounded-md bg-blue-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-blue-700"
      >
        {{ acceso.etiqueta }}
      </RouterLink>
    </div>
  </div>
</template>