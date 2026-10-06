<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// `mensaje` tiene la forma `{ role: 'user' | 'assistant', content: string }`.
const props = defineProps({
  mensaje: {
    type: Object,
    required: true,
  },
})

const esUsuario = computed(() => props.mensaje.role === 'user')

// `breaks: true` convierte cada salto de línea simple en <br>, para que el
// texto del agente respete los saltos tal como los emite. `gfm` (activo por
// defecto) habilita tablas, tachado y listas de tareas.
const htmlRenderizado = computed(() => {
  if (esUsuario.value) return ''
  const html = marked.parse(props.mensaje.content ?? '', { breaks: true })
  // El contenido viene del LLM (fuente no confiable): se sanitiza el HTML
  // antes de inyectarlo con v-html para bloquear scripts y handlers.
  return DOMPurify.sanitize(html)
})
</script>

<template>
  <div class="flex" :class="esUsuario ? 'justify-end' : 'justify-start'">
    <!-- El mensaje del usuario se muestra como texto plano: puede contener
         símbolos literales que no deben interpretarse como Markdown. -->
    <div
      v-if="esUsuario"
      class="max-w-md whitespace-pre-wrap rounded-t-xl rounded-bl-xl rounded-br-none bg-blue-600 px-4 py-2 text-sm text-white"
    >
      {{ mensaje.content }}
    </div>

    <!-- El mensaje del asistente se renderiza como Markdown (sanitizado). -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div
      v-else
      class="markdown max-w-md rounded-t-xl rounded-br-xl rounded-bl-none border border-gray-200 bg-white px-4 py-2 text-sm text-gray-800"
      v-html="htmlRenderizado"
    ></div>
  </div>
</template>

<style scoped>
/* Estilos del HTML generado por `marked`: como se inyecta con v-html, Vue no
   le aplica el atributo de scoped directamente y hay que usar :deep(). */

.markdown :deep(p) {
  margin: 0.375rem 0;
}

.markdown :deep(p:first-child) {
  margin-top: 0;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(strong) {
  font-weight: 600;
}

.markdown :deep(em) {
  font-style: italic;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: 0.5rem 0 0.25rem;
  font-weight: 600;
}

.markdown :deep(ul) {
  margin: 0.375rem 0;
  padding-left: 1.25rem;
  list-style: disc;
}

.markdown :deep(ol) {
  margin: 0.375rem 0;
  padding-left: 1.25rem;
  list-style: decimal;
}

.markdown :deep(li) {
  margin: 0.125rem 0;
}

.markdown :deep(code) {
  border-radius: 0.25rem;
  background-color: #f3f4f6;
  padding: 0.125rem 0.25rem;
  font-size: 0.8125rem;
}

.markdown :deep(pre) {
  margin: 0.5rem 0;
  overflow-x: auto;
  border-radius: 0.5rem;
  background-color: #f3f4f6;
  padding: 0.5rem 0.75rem;
}

.markdown :deep(pre code) {
  background-color: transparent;
  padding: 0;
}

.markdown :deep(a) {
  color: #2563eb;
  text-decoration: underline;
}

.markdown :deep(blockquote) {
  margin: 0.5rem 0;
  border-left: 3px solid #d1d5db;
  padding-left: 0.75rem;
  color: #4b5563;
}

.markdown :deep(table) {
  margin: 0.5rem 0;
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 0.375rem 0.5rem;
  text-align: left;
}

.markdown :deep(th) {
  background-color: #f9fafb;
  font-weight: 600;
}

.markdown :deep(hr) {
  margin: 0.75rem 0;
  border-color: #e5e7eb;
}
</style>
