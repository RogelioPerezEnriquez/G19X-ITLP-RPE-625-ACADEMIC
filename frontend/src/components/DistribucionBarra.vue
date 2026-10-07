<script setup>
import { computed } from 'vue'

const props = defineProps({
  etiqueta: {
    type: String,
    required: true,
  },
  valor: {
    type: Number,
    required: true,
  },
  total: {
    type: Number,
    required: true,
  },
  color: {
    type: String,
    default: 'bg-blue-500',
  },
})

// Formato español: decimal con "," (p. ej. "66,7 %").
const formateador = new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 1,
})

// Porcentaje del valor sobre el total; con total 0 se muestra 0 para evitar
// divisiones por cero.
const porcentaje = computed(() => {
  if (!props.total || props.total <= 0) return 0
  return (props.valor / props.total) * 100
})

const porcentajeFormateado = computed(() => `${formateador.format(porcentaje.value)} %`)

const valorFormateado = computed(() => formateador.format(props.valor))

// El ancho de la barra se acota a [0, 100] para no romper el layout.
const anchoPct = computed(() => Math.min(100, Math.max(0, porcentaje.value)))
</script>

<template>
  <div>
    <div class="mb-1 flex items-center justify-between text-sm">
      <span class="font-medium text-gray-700">{{ etiqueta }}</span>
      <span class="text-gray-900">
        <span class="font-medium">{{ valorFormateado }}</span>
        <span class="text-gray-500"> ({{ porcentajeFormateado }})</span>
      </span>
    </div>
    <div
      class="w-full bg-gray-200 rounded-full h-2"
      role="progressbar"
      :aria-valuenow="anchoPct"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="etiqueta"
    >
      <div
        class="h-2 rounded-full"
        :class="color"
        :style="{ width: anchoPct + '%' }"
      ></div>
    </div>
  </div>
</template>
