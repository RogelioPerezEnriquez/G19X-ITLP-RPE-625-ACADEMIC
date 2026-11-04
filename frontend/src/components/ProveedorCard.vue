<script setup>
import { computed } from 'vue'
import ScoreBadge from './ScoreBadge.vue'
import BarraProgreso from './BarraProgreso.vue'
// Formato mexicano centralizado con un decimal (p. ej. "96.2"): el score
// siempre se muestra con un decimal para que los cortes de estado sean
// legibles (60.0 vs 60).
import { score } from '../utils/formato'

const props = defineProps({
  proveedor: {
    type: Object,
    required: true,
  },
})

const scoreFormateado = computed(() => {
  const numero = Number(props.proveedor.score)
  return Number.isFinite(numero) ? score.format(numero) : '—'
})
</script>

<template>
  <article
    class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md"
  >
    <div class="flex items-start justify-between gap-3">
      <h3 class="text-lg font-bold text-gray-900">
        {{ proveedor.nombre }}
      </h3>
      <ScoreBadge :estado="proveedor.estado" />
    </div>

    <p class="mt-2 text-3xl font-semibold text-gray-900">
      {{ scoreFormateado }}
      <span class="text-sm font-normal text-gray-500">/ 100</span>
    </p>

    <div class="mt-4 space-y-3">
      <BarraProgreso
        :valor="proveedor.cumplimiento_entrega_pct"
        etiqueta="Cumplimiento de entrega"
        color="bg-green-500"
      />
      <BarraProgreso
        :valor="proveedor.tasa_defectos_pct"
        etiqueta="Tasa de defectos"
        color="bg-red-500"
      />
    </div>
  </article>
</template>
