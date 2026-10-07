<script setup>
import { computed, onMounted } from 'vue'
import { useKpisStore } from '../stores/kpis'
import KpiCard from '../components/KpiCard.vue'
import DistribucionBarra from '../components/DistribucionBarra.vue'
import GridABCXYZ from '../components/GridABCXYZ.vue'
import UrgenciaBadge from '../components/UrgenciaBadge.vue'

const kpisStore = useKpisStore()

// Formato español: separador de miles "." y decimal "," (p. ej. 1.470,64).
// `useGrouping: 'always'` es necesario porque el español, por defecto
// (minimumGroupingDigits = 2), omite el separador de miles en números de
// cuatro cifras y devolvería "1470,64" en lugar de "1.470,64".
const formateadorMoneda = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: 'always',
})

const formateadorPorcentaje = new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 1,
})

const metricas = computed(() => kpisStore.metricas)

const hayDatos = computed(() => metricas.value.total_recomendaciones > 0)

// El ahorro neto se expresa en pesos mexicanos con el símbolo "$".
const ahorroFormateado = computed(() => {
  const numero = Number(metricas.value.suma_ahorro_neto)
  return Number.isFinite(numero) ? `$${formateadorMoneda.format(numero)}` : '—'
})

const porcentajeConAhorro = computed(() => {
  const total = metricas.value.total_recomendaciones
  if (!total) return '0 %'
  const porcentaje = (metricas.value.con_ahorro_detectado / total) * 100
  return `${formateadorPorcentaje.format(porcentaje)} %`
})

const URGENCIAS = [
  { etiqueta: 'Crítico', color: 'bg-red-500' },
  { etiqueta: 'Atención', color: 'bg-yellow-500' },
  { etiqueta: 'Sin riesgo', color: 'bg-green-500' },
]

const CLASES_ABC = [
  { etiqueta: 'A', color: 'bg-blue-500' },
  { etiqueta: 'B', color: 'bg-indigo-500' },
  { etiqueta: 'C', color: 'bg-purple-500' },
]

const CLASES_XYZ = [
  { etiqueta: 'X', color: 'bg-teal-500' },
  { etiqueta: 'Y', color: 'bg-cyan-500' },
  { etiqueta: 'Z', color: 'bg-orange-500' },
]

onMounted(() => {
  kpisStore.calcular()
})
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold text-gray-900">Panel de KPIs</h1>

    <div
      v-if="kpisStore.cargando"
      class="flex items-center justify-center gap-3 rounded-lg bg-white p-8 text-gray-600 shadow-sm"
    >
      <span
        class="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"
        aria-hidden="true"
      ></span>
      Cargando...
    </div>

    <div
      v-else-if="kpisStore.error"
      class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
    >
      <p>{{ kpisStore.error }}</p>
      <button
        type="button"
        class="mt-2 font-medium underline"
        @click="kpisStore.calcular()"
      >
        Reintentar
      </button>
    </div>

    <p
      v-else-if="!hayDatos"
      class="rounded-lg bg-white p-8 text-center text-gray-600 shadow-sm"
    >
      No hay datos para mostrar.
    </p>

    <div v-else class="space-y-6">
      <!-- Fila 1: tarjetas principales -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          titulo="Total de recomendaciones"
          :valor="metricas.total_recomendaciones"
          color="bg-blue-500"
        />
        <KpiCard
          titulo="Ahorro neto total"
          :valor="ahorroFormateado"
          subtitulo="Pesos mexicanos"
          color="bg-green-500"
        />
        <KpiCard
          titulo="Con ahorro detectado"
          :valor="metricas.con_ahorro_detectado"
          :subtitulo="`${porcentajeConAhorro} del total`"
          color="bg-teal-500"
        />
        <KpiCard
          titulo="Productos únicos"
          :valor="metricas.productos_unicos"
          color="bg-indigo-500"
        />
      </div>
      <!-- Fila 2: urgencias -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div
          v-for="urgencia in URGENCIAS"
          :key="urgencia.etiqueta"
          class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
        >
          <div class="flex items-center justify-between">
            <p class="text-sm text-gray-500">{{ urgencia.etiqueta }}</p>
            <UrgenciaBadge :urgencia="urgencia.etiqueta" />
          </div>
          <p class="mt-2 text-3xl font-bold text-gray-900">
            {{ metricas.por_urgencia[urgencia.etiqueta] ?? 0 }}
          </p>
        </div>
      </div>

      <!-- Fila 3: distribuciones ABC y XYZ -->
      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 class="mb-4 text-base font-semibold text-gray-900">
            Distribución ABC
          </h2>
          <div class="space-y-3">
            <DistribucionBarra
              v-for="clase in CLASES_ABC"
              :key="clase.etiqueta"
              :etiqueta="clase.etiqueta"
              :valor="metricas.por_clase_abc[clase.etiqueta] ?? 0"
              :total="metricas.total_recomendaciones"
              :color="clase.color"
            />
          </div>
        </div>

        <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h2 class="mb-4 text-base font-semibold text-gray-900">
            Distribución XYZ
          </h2>
          <div class="space-y-3">
            <DistribucionBarra
              v-for="clase in CLASES_XYZ"
              :key="clase.etiqueta"
              :etiqueta="clase.etiqueta"
              :valor="metricas.por_clase_xyz[clase.etiqueta] ?? 0"
              :total="metricas.total_recomendaciones"
              :color="clase.color"
            />
          </div>
        </div>
      </div>

      <!-- Fila 4: grid ABC × XYZ -->
      <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h2 class="mb-4 text-base font-semibold text-gray-900">
          Matriz ABC × XYZ
        </h2>
        <div class="mx-auto max-w-md">
          <GridABCXYZ :distribucion="metricas.por_combinacion_abc_xyz" />
        </div>
        <div class="mt-4 flex flex-wrap justify-center gap-4 text-xs text-gray-500">
          <span class="flex items-center gap-1.5">
            <span class="h-3 w-3 rounded-sm bg-green-100 ring-1 ring-gray-200"></span>
            Importancia alta
          </span>
          <span class="flex items-center gap-1.5">
            <span class="h-3 w-3 rounded-sm bg-yellow-100 ring-1 ring-gray-200"></span>
            Importancia media
          </span>
          <span class="flex items-center gap-1.5">
            <span class="h-3 w-3 rounded-sm bg-red-100 ring-1 ring-gray-200"></span>
            Importancia baja
          </span>
        </div>
      </div>
    </div>
  </section>
</template>

