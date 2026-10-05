<script setup>
import { computed } from 'vue'

const props = defineProps({
  estado: {
    type: String,
    required: true,
  },
})

// Color de Tailwind por estado. Las claves deben coincidir con las etiquetas
// que calcula el store (`calcularEstado` en `stores/proveedores.js`).
const COLORES = {
  'Confiable': 'bg-green-100 text-green-800',
  'Aceptable con reservas': 'bg-yellow-100 text-yellow-800',
  'Riesgoso': 'bg-red-100 text-red-800',
}

const clases = computed(() => COLORES[props.estado] ?? 'bg-gray-100 text-gray-800')
</script>

<template>
  <span
    class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
    :class="clases"
  >
    {{ estado }}
  </span>
</template>
