<script setup>
import { ref } from 'vue'

const props = defineProps({
  // Mientras el agente responde, el campo y el botón quedan deshabilitados.
  cargando: {
    type: Boolean,
    default: false,
  },
  placeholder: {
    type: String,
    default: 'Escribe tu consulta...',
  },
})

const emit = defineEmits(['enviar'])

const texto = ref('')

function enviar() {
  const mensaje = texto.value.trim()
  if (!mensaje || props.cargando) return
  emit('enviar', mensaje)
  texto.value = ''
}

// Enter envía; Shift+Enter inserta un salto de línea (comportamiento por
// defecto del textarea, así que no se intercepta).
function alPresionarEnter(evento) {
  if (evento.shiftKey) return
  evento.preventDefault()
  enviar()
}
</script>

<template>
  <div class="flex items-end gap-2">
    <textarea
      v-model="texto"
      rows="2"
      :placeholder="placeholder"
      :disabled="cargando"
      class="flex-1 resize-none rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-400"
      @keydown.enter="alPresionarEnter"
    ></textarea>
    <button
      type="button"
      :disabled="cargando || !texto.trim()"
      class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
      @click="enviar"
    >
      Enviar
    </button>
  </div>
</template>
