<script setup>
import { computed } from 'vue'

const props = defineProps({
  urgencia: {
    type: String,
    required: true,
  },
})

// Color de Tailwind por urgencia. La clave "Sin riesgo" debe coincidir con la
// etiqueta que calcula el store.
const COLORES = {
  'Crítico': 'bg-red-100 text-red-800',
  'Atención': 'bg-yellow-100 text-yellow-800',
  'Sin riesgo': 'bg-green-100 text-green-800',
}

const clases = computed(() => COLORES[props.urgencia] ?? 'bg-gray-100 text-gray-800')
</script>

<template>
  <span
    class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
    :class="clases"
  >
    {{ urgencia }}
  </span>
</template>
