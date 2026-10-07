<script setup>
defineProps({
  titulo: {
    type: String,
    required: true,
  },
  valor: {
    type: [Number, String],
    required: true,
  },
  subtitulo: {
    type: String,
    default: '',
  },
  // Clase de Tailwind para la franja superior de la tarjeta.
  color: {
    type: String,
    default: 'bg-blue-500',
  },
})
</script>

<template>
  <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
    <div class="h-1.5" :class="color" aria-hidden="true"></div>
    <div class="p-4">
      <p class="text-sm text-gray-500">{{ titulo }}</p>
      <p class="mt-1 text-3xl font-bold text-gray-900">{{ valor }}</p>
      <p v-if="subtitulo" class="mt-1 text-sm text-gray-500">{{ subtitulo }}</p>
    </div>
  </div>
</template>
