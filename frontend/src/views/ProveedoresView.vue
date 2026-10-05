<script setup>
import { computed, onMounted, ref } from 'vue'
import { useProveedoresStore, ORDEN_ESTADO } from '../stores/proveedores'
import ProveedorCard from '../components/ProveedorCard.vue'

const store = useProveedoresStore()

// "Todos" no filtra; el resto se compara contra el estado calculado.
const OPCIONES_ESTADO = [
  { etiqueta: 'Todos', valor: 'Todos' },
  ...ORDEN_ESTADO.map((estado) => ({ etiqueta: estado, valor: estado })),
]

const filtroEstado = ref('Todos')

const itemsFiltrados = computed(() => {
  if (filtroEstado.value === 'Todos') return store.items
  return store.porEstado(filtroEstado.value)
})

onMounted(() => {
  store.listar()
})
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-2xl font-semibold text-gray-900">Proveedores</h1>

    <div class="flex flex-wrap gap-2">
      <button
        v-for="opcion in OPCIONES_ESTADO"
        :key="opcion.valor"
        type="button"
        class="rounded-full px-3 py-1.5 text-sm font-medium transition"
        :class="
          filtroEstado === opcion.valor
            ? 'bg-blue-600 text-white'
            : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
        "
        @click="filtroEstado = opcion.valor"
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
          ? 'No hay proveedores registrados.'
          : 'No hay proveedores con ese estado.'
      }}
    </p>

    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      <ProveedorCard
        v-for="item in itemsFiltrados"
        :key="item.id"
        :proveedor="item"
      />
    </div>
  </section>
</template>
