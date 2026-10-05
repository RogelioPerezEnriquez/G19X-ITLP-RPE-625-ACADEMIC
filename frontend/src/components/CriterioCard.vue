<script setup>
import { computed } from 'vue'
import { CRITERIOS_POR_KEY } from '../constants/criterios'

const props = defineProps({
  criterio: {
    type: String,
    required: true,
  },
  estado: {
    type: String,
    default: null,
  },
  valorNumerico: {
    type: Number,
    default: null,
  },
})

// Si llega un criterio desconocido, se muestra su key como título en lugar de
// romper la tarjeta.
const definicion = computed(
  () =>
    CRITERIOS_POR_KEY[props.criterio] ?? {
      titulo: props.criterio,
      descripcion: '',
      unidad: null,
    }
)

const ESTADOS_POSITIVOS = [
  'Confiable',
  'Óptima',
  'Alta confianza',
  'Alta',
  'Ahorro detectado',
  'Sin riesgo',
]

const ESTADOS_MEDIOS = [
  'Atención',
  'Confianza moderada',
  'Media',
  'Aceptable con reservas',
]

const ESTADOS_NEGATIVOS = [
  'Crítico',
  'Pedido muy pequeño',
  'Pedido excesivo',
  'Baja confianza (revisión manual)',
  'Baja',
  'Riesgoso',
  'Sin oportunidad adicional',
]

const CLASE_VERDE = 'bg-green-100 text-green-800'
const CLASE_AMARILLO = 'bg-yellow-100 text-yellow-800'
const CLASE_ROJO = 'bg-red-100 text-red-800'
const CLASE_NEUTRO = 'bg-gray-100 text-gray-800'

// Mapea el estado del criterio a las clases de color del badge. Un estado no
// reconocido (o ausente) queda en gris neutro.
function colorDeEstado(estado) {
  if (ESTADOS_POSITIVOS.includes(estado)) return CLASE_VERDE
  if (ESTADOS_MEDIOS.includes(estado)) return CLASE_AMARILLO
  if (ESTADOS_NEGATIVOS.includes(estado)) return CLASE_ROJO
  return CLASE_NEUTRO
}

const clasesBadge = computed(() => colorDeEstado(props.estado))

// Formato español: separador de miles "." y decimal ",". `useGrouping:
// 'always'` fuerza el separador en números de cuatro cifras (el español, por
// defecto, lo omite: "1470,64" en lugar de "1.470,64").
const formateadorMoneda = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: 'always',
})

const formateadorNumero = new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 4,
  useGrouping: 'always',
})

const valorFormateado = computed(() => {
  if (props.valorNumerico === null || props.valorNumerico === undefined) {
    return '—'
  }

  const unidad = definicion.value.unidad
  if (unidad === '$') {
    return `$ ${formateadorMoneda.format(props.valorNumerico)}`
  }

  const numero = formateadorNumero.format(props.valorNumerico)
  return unidad ? `${numero} ${unidad}` : numero
})
</script>

<template>
  <article class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
    <div class="flex items-start justify-between gap-3">
      <h3 class="text-base font-bold text-gray-900">
        {{ definicion.titulo }}
      </h3>
      <span
        class="inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
        :class="clasesBadge"
      >
        {{ estado ?? 'Sin evaluar' }}
      </span>
    </div>

    <p v-if="definicion.descripcion" class="mt-1 text-sm text-gray-500">
      {{ definicion.descripcion }}
    </p>

    <p class="mt-3 text-lg font-semibold text-gray-900">
      {{ valorFormateado }}
    </p>
  </article>
</template>
