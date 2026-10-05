<script setup>
import { computed } from 'vue'

const props = defineProps({
  valor: {
    type: Number,
    required: true,
  },
  etiqueta: {
    type: String,
    default: '',
  },
  color: {
    type: String,
    default: 'bg-blue-500',
  },
})

// Formato español: decimal con "," (p. ej. "95 %" o "96,2 %"). No fuerza
// decimales: un valor entero se muestra como "95 %".
const formateador = new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 1,
})

const valorFormateado = computed(() => {
  const numero = Number(props.valor)
  return Number.isFinite(numero) ? `${formateador.format(numero)} %` : '—'
})

// El ancho de la barra se acota a [0, 100] para que un valor fuera de rango no
// rompa el layout (el texto muestra el valor real).
const anchoPct = computed(() => {
  const numero = Number(props.valor)
  if (!Number.isFinite(numero)) return 0
  return Math.min(100, Math.max(0, numero))
})
</script>

<template>
  <div>
    <div v-if="etiqueta" class="mb-1 flex items-center justify-between text-sm">
      <span class="text-gray-500">{{ etiqueta }}</span>
      <span class="font-medium text-gray-900">{{ valorFormateado }}</span>
    </div>
    <div
      class="w-full bg-gray-200 rounded-full h-2"
      role="progressbar"
      :aria-valuenow="anchoPct"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="etiqueta || 'Progreso'"
    >
      <div
        class="h-2 rounded-full"
        :class="color"
        :style="{ width: anchoPct + '%' }"
      ></div>
    </div>
  </div>
</template>
