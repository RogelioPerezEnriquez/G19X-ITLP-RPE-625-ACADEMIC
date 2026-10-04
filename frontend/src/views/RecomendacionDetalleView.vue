<script setup>
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="bg-white rounded-lg shadow p-6">
    <h2 class="text-lg font-medium text-gray-900 mb-2">
      Detalle del producto {{ route.params.productoId }}
    </h2>
    <p class="text-gray-600">
      El panel de explicabilidad estará disponible próximamente.
    </p>

    <RouterLink
      to="/recomendaciones"
      class="mt-4 inline-block text-sm font-medium text-blue-600 hover:underline"
    >
      Volver a recomendaciones
    </RouterLink>
  </div>
</template>
