<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import UrgenciaBadge from './UrgenciaBadge.vue'

const props = defineProps({
  recomendacion: {
    type: Object,
    required: true,
  },
})

// Formato español: separador de miles "." y decimal "," (p. ej. 1.470,64).
// `useGrouping: 'always'` es necesario porque el español, por defecto
// (minimumGroupingDigits = 2), omite el separador de miles en números de
// cuatro cifras y devolvería "1470,64" en lugar de "1.470,64".
const formateadorDecimales = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: 'always',
})

// Las cantidades no fuerzan decimales (5.000 en lugar de 5.000,00).
const formateadorCantidad = new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 2,
  useGrouping: 'always',
})

function formatearDecimal(valor) {
  const numero = Number(valor)
  return Number.isFinite(numero) ? formateadorDecimales.format(numero) : '—'
}

function formatearCantidad(valor) {
  const numero = Number(valor)
  return Number.isFinite(numero) ? formateadorCantidad.format(numero) : '—'
}

const clasificacion = computed(() => {
  const { clase_abc: abc, clase_xyz: xyz } = props.recomendacion
  if (!abc || !xyz) return null
  return `${abc}/${xyz}`
})

const ahorroFormateado = computed(() =>
  formatearDecimal(props.recomendacion.ahorro_neto_estimado)
)

const cantidadFormateada = computed(() =>
  formatearCantidad(props.recomendacion.cantidad_recomendada)
)
</script>

<template>
  <RouterLink
    :to="{
      name: 'recomendacionDetalle',
      params: { productoId: recomendacion.producto_id },
    }"
    class="block rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 class="truncate text-base font-bold text-gray-900">
          {{ recomendacion.producto_nombre }}
        </h3>
        <p class="truncate text-sm text-gray-500">
          {{ recomendacion.proveedor_nombre }}
        </p>
      </div>
      <UrgenciaBadge :urgencia="recomendacion.urgencia" />
    </div>

    <div class="mt-3 flex flex-wrap items-center gap-2">
      <span
        v-if="clasificacion"
        class="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700"
        title="Clasificación ABC/XYZ"
      >
        {{ clasificacion }}
      </span>
    </div>

    <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
      <div>
        <dt class="text-gray-500">Ahorro neto estimado</dt>
        <dd class="font-medium text-gray-900">{{ ahorroFormateado }}</dd>
      </div>
      <div>
        <dt class="text-gray-500">Cantidad recomendada</dt>
        <dd class="font-medium text-gray-900">{{ cantidadFormateada }}</dd>
      </div>
    </dl>
  </RouterLink>
</template>
