<script setup>
import { computed } from 'vue'

const props = defineProps({
  // Objeto con las 9 combinaciones: { AX: N, AY: N, ..., CZ: N }.
  distribucion: {
    type: Object,
    required: true,
  },
})

const FILAS = ['A', 'B', 'C']
const COLUMNAS = ['X', 'Y', 'Z']

// Importancia de cada combinación según la rúbrica del MVP (criterio 4,
// docs/mvp.md §10). Define también el color de fondo de la celda.
const IMPORTANCIA = {
  AX: 'Alta', AY: 'Alta', AZ: 'Media',
  BX: 'Alta', BY: 'Media', BZ: 'Media',
  CX: 'Media', CY: 'Baja', CZ: 'Baja',
}

const COLORES = {
  Alta: 'bg-green-100',
  Media: 'bg-yellow-100',
  Baja: 'bg-red-100',
}

const celdas = computed(() =>
  FILAS.map((fila) =>
    COLUMNAS.map((columna) => {
      const clave = `${fila}${columna}`
      return {
        clave,
        valor: Number(props.distribucion?.[clave] ?? 0),
        color: COLORES[IMPORTANCIA[clave]],
      }
    })
  )
)
</script>

<template>
  <div class="grid grid-cols-4 gap-2 text-center">
    <!-- Encabezados de columna (la primera celda queda vacía, es la esquina) -->
    <div aria-hidden="true"></div>
    <div
      v-for="columna in COLUMNAS"
      :key="columna"
      class="py-1 text-sm font-semibold text-gray-600"
    >
      {{ columna }}
    </div>

    <!-- Filas: encabezado (A, B, C) + 3 celdas -->
    <template v-for="(fila, indiceFila) in FILAS" :key="fila">
      <div class="flex items-center justify-center text-sm font-semibold text-gray-600">
        {{ fila }}
      </div>
      <div
        v-for="celda in celdas[indiceFila]"
        :key="celda.clave"
        class="rounded-md border border-gray-200 py-4 text-lg font-bold text-gray-900"
        :class="celda.color"
        :title="`Combinación ${celda.clave}: importancia ${IMPORTANCIA[celda.clave]}`"
      >
        {{ celda.valor }}
      </div>
    </template>
  </div>
</template>
