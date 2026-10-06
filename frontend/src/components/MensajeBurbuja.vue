<script setup>
import { computed } from 'vue'

// `mensaje` tiene la forma `{ role: 'user' | 'assistant', content: string }`.
const props = defineProps({
  mensaje: {
    type: Object,
    required: true,
  },
})

const esUsuario = computed(() => props.mensaje.role === 'user')
</script>

<template>
  <div class="flex" :class="esUsuario ? 'justify-end' : 'justify-start'">
    <div
      class="max-w-md px-4 py-2 text-sm whitespace-pre-wrap"
      :class="
        esUsuario
          ? 'rounded-t-xl rounded-bl-xl rounded-br-none bg-blue-600 text-white'
          : 'rounded-t-xl rounded-br-xl rounded-bl-none border border-gray-200 bg-white text-gray-800'
      "
    >
      {{ mensaje.content }}
    </div>
  </div>
</template>
