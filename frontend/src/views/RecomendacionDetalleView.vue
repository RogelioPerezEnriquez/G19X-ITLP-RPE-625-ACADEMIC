<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRecomendacionesStore } from '../stores/recomendaciones'
import { CRITERIOS_ORDENADOS } from '../constants/criterios'
import CriterioCard from '../components/CriterioCard.vue'
// Formato mexicano centralizado: cantidades "5,000", montos "$1,470.64" y
// valores precisos como el CV de la demanda.
import { moneda, numero, numeroPreciso } from '../utils/formato'

const route = useRoute()
const router = useRouter()
const store = useRecomendacionesStore()

// El parámetro de la ruta puede ser el nombre del producto o su UUID; el
// store decide por cuál columna filtrar.
const productoId = computed(() => String(route.params.productoId ?? ''))

onMounted(() => {
  store.detalle(productoId.value)
})

// Si se navega de un detalle a otro sin desmontar la vista, se recarga.
watch(productoId, (nuevoId) => {
  if (nuevoId) store.detalle(nuevoId)
})

const detalle = computed(() => store.detalleActual)

const nombreProducto = computed(
  () => detalle.value?.producto?.nombre ?? productoId.value
)

const subtitulo = computed(() => {
  const d = detalle.value
  if (!d) return ''
  const partes = []
  if (d.proveedor?.nombre) partes.push(`Proveedor: ${d.proveedor.nombre}`)
  if (d.clase_abc && d.clase_xyz) {
    partes.push(`Clasificación ${d.clase_abc}/${d.clase_xyz}`)
  }
  return partes.join(' · ')
})

// Las tarjetas se muestran siempre en el orden definido en las constantes,
// aunque alguna evaluación falte (en ese caso queda "Sin evaluar" y "—").
const criteriosConEvaluacion = computed(() => {
  const evaluaciones = detalle.value?.evaluaciones ?? []
  return CRITERIOS_ORDENADOS.map((definicion) => {
    const evaluacion =
      evaluaciones.find((e) => e.criterio === definicion.key) ?? null
    const valor = evaluacion?.valor_numerico
    return {
      key: definicion.key,
      estado: evaluacion?.estado ?? null,
      valorNumerico:
        valor === null || valor === undefined ? null : Number(valor),
    }
  })
})

function formatearCon(formateador, valor) {
  if (valor === null || valor === undefined) return '—'
  const valorNumerico = Number(valor)
  return Number.isFinite(valorNumerico) ? formateador.format(valorNumerico) : '—'
}

function formatearMoneda(valor) {
  if (valor === null || valor === undefined) return '—'
  const monto = Number(valor)
  return Number.isFinite(monto) ? moneda.format(monto) : '—'
}

function formatearDias(valor) {
  const texto = formatearCon(numero, valor)
  return texto === '—' ? texto : `${texto} días`
}

const datosRecomendacion = computed(() => {
  const d = detalle.value
  if (!d) return []
  return [
    { etiqueta: 'Demanda estimada', valor: formatearCon(numero, d.demanda_estimada) },
    { etiqueta: 'CV de la demanda', valor: formatearCon(numeroPreciso, d.cv_demanda) },
    { etiqueta: 'Punto de reorden', valor: formatearCon(numero, d.punto_reorden) },
    { etiqueta: 'Stock de seguridad', valor: formatearCon(numero, d.stock_seguridad) },
    { etiqueta: 'Cantidad EOQ', valor: formatearCon(numero, d.cantidad_eoq) },
    { etiqueta: 'Cantidad recomendada', valor: formatearCon(numero, d.cantidad_recomendada) },
    { etiqueta: 'Lead time', valor: formatearDias(d.lead_time_dias) },
    { etiqueta: 'Precio unitario', valor: formatearMoneda(d.precio_unitario) },
    { etiqueta: 'Ahorro neto estimado', valor: formatearMoneda(d.ahorro_neto_estimado) },
    { etiqueta: 'Stock actual', valor: formatearCon(numero, d.producto?.stock_actual) },
  ]
})

function volver() {
  router.push({ name: 'recomendaciones' })
}
</script>

<template>
  <section class="space-y-6">
    <div
      v-if="store.cargando"
      class="flex items-center justify-center gap-3 rounded-lg bg-white p-8 text-gray-600 shadow-sm"
    >
      <span
        class="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"
        aria-hidden="true"
      ></span>
      Cargando...
    </div>

    <div
      v-else-if="store.error"
      class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
    >
      <p>{{ store.error }}</p>
      <button
        type="button"
        class="mt-2 font-medium underline"
        @click="store.detalle(productoId)"
      >
        Reintentar
      </button>
    </div>

    <div
      v-else-if="!detalle"
      class="rounded-lg bg-white p-8 text-center text-gray-600 shadow-sm"
    >
      <p>Producto no encontrado.</p>
      <button
        type="button"
        class="mt-4 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        @click="volver"
      >
        Volver a recomendaciones
      </button>
    </div>

    <template v-else>
      <header>
        <h1 class="text-2xl font-semibold text-gray-900">
          Detalle de {{ nombreProducto }}
        </h1>
        <p v-if="subtitulo" class="mt-1 text-sm text-gray-500">
          {{ subtitulo }}
        </p>
      </header>

      <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <CriterioCard
          v-for="criterio in criteriosConEvaluacion"
          :key="criterio.key"
          :criterio="criterio.key"
          :estado="criterio.estado"
          :valor-numerico="criterio.valorNumerico"
          :clase-abc="detalle.clase_abc"
          :clase-xyz="detalle.clase_xyz"
        />
      </div>

      <section class="rounded-lg bg-white p-6 shadow-sm">
        <h2 class="text-lg font-medium text-gray-900">
          Datos de la recomendación
        </h2>
        <dl class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <div v-for="dato in datosRecomendacion" :key="dato.etiqueta">
            <dt class="text-sm text-gray-500">{{ dato.etiqueta }}</dt>
            <dd class="mt-0.5 font-medium text-gray-900">{{ dato.valor }}</dd>
          </div>
        </dl>
      </section>

      <div>
        <button
          type="button"
          class="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          @click="volver"
        >
          Volver
        </button>
      </div>
    </template>
  </section>
</template>

