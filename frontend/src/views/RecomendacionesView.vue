<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRecomendacionesStore } from '../stores/recomendaciones'
import RecomendacionCard from '../components/RecomendacionCard.vue'

const store = useRecomendacionesStore()

// "Todas" no filtra; el resto se compara contra la urgencia calculada.
const OPCIONES_URGENCIA = [
  { etiqueta: 'Todas', valor: 'Todas' },
  { etiqueta: 'Críticas', valor: 'Crítico' },
  { etiqueta: 'Atención', valor: 'Atención' },
  { etiqueta: 'Sin riesgo', valor: 'Sin riesgo' },
]

const filtroUrgencia = ref('Todas')

const itemsFiltrados = computed(() => {
  if (filtroUrgencia.value === 'Todas') return store.items
  return store.porUrgencia(filtroUrgencia.value)
})

onMounted(() => {
  store.listar()
})
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold text-gray-900">
      Recomendaciones de compra
    </h1>

    <div class="flex flex-wrap gap-2">
      <button
        v-for="opcion in OPCIONES_URGENCIA"
        :key="opcion.valor"
        type="button"
        class="rounded-full px-3 py-1.5 text-sm font-medium transition"
        :class="
          filtroUrgencia === opcion.valor
            ? 'bg-blue-600 text-white'
            : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
        "
        @click="filtroUrgencia = opcion.valor"
      >
        {{ opcion.etiqueta }}
      </button>
    </div>

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
        @click="store.listar()"
      >
        Reintentar
      </button>
    </div>

    <p
      v-else-if="itemsFiltrados.length === 0"
      class="rounded-lg bg-white p-8 text-center text-gray-600 shadow-sm"
    >
      {{
        store.items.length === 0
          ? 'No hay recomendaciones registradas.'
          : 'No hay recomendaciones con esa urgencia.'
      }}
    </p>

    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      <RecomendacionCard
        v-for="item in itemsFiltrados"
        :key="item.id ?? item.producto_id"
        :recomendacion="item"
      />
    </div>
  </section>
</template>
