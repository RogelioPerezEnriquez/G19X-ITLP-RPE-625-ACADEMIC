<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { useChatStore } from '../stores/chat'
import MensajeBurbuja from '../components/MensajeBurbuja.vue'
import IndicadorEscribiendo from '../components/IndicadorEscribiendo.vue'
import ChatInput from '../components/ChatInput.vue'

const chatStore = useChatStore()

// Referencia al área con scroll para poder bajar al último mensaje.
const contenedorMensajes = ref(null)

// Preguntas frecuentes: se muestran solo cuando el chat está en su estado
// inicial (únicamente el mensaje de bienvenida del asistente).
const SUGERENCIAS = [
  '¿Hay recomendaciones críticas?',
  'Dame un resumen de prioridades ABC/XYZ',
  '¿Qué productos están en atención?',
  'Dame el detalle de SEED_Widget A',
]

// Espera a que Vue pinte el DOM antes de mover el scroll, para que el alto
// del contenedor ya incluya el mensaje nuevo.
async function desplazarAlFinal() {
  await nextTick()
  const contenedor = contenedorMensajes.value
  if (contenedor) {
    contenedor.scrollTop = contenedor.scrollHeight
  }
}

// Baja el scroll cuando llega un mensaje nuevo y también cuando aparece el
// indicador de "escribiendo...".
watch(() => chatStore.mensajes.length, desplazarAlFinal)
watch(
  () => chatStore.cargando,
  (cargando) => {
    if (cargando) desplazarAlFinal()
  },
)

onMounted(() => {
  chatStore.inicializar()
  desplazarAlFinal()
})

function limpiarChat() {
  chatStore.limpiar()
  // Tras vaciar, se restaura el mensaje de bienvenida.
  chatStore.inicializar()
}
</script>

<template>
  <section class="flex h-[calc(100vh-180px)] flex-col space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900">Asistente de compras</h1>
      <button
        type="button"
        class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        @click="limpiarChat"
      >
        Limpiar chat
      </button>
    </div>

    <div
      ref="contenedorMensajes"
      class="flex-1 space-y-3 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4"
    >
      <MensajeBurbuja
        v-for="(mensaje, indice) in chatStore.mensajes"
        :key="indice"
        :mensaje="mensaje"
      />

      <IndicadorEscribiendo v-if="chatStore.cargando" />

      <div
        v-if="chatStore.mensajes.length <= 1 && !chatStore.cargando"
        class="flex flex-wrap gap-2 pt-2"
      >
        <button
          v-for="sugerencia in SUGERENCIAS"
          :key="sugerencia"
          type="button"
          class="rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-100"
          @click="chatStore.enviar(sugerencia)"
        >
          {{ sugerencia }}
        </button>
      </div>
    </div>

    <ChatInput
      :cargando="chatStore.cargando"
      placeholder="Escribe tu consulta sobre compras, stock o proveedores..."
      @enviar="chatStore.enviar"
    />
  </section>
</template>
