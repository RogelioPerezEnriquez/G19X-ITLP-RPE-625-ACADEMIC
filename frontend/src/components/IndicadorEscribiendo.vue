<script setup>
// Retardos escalonados para que los tres puntos reboten en secuencia.
// Tailwind no expone `animation-delay` como utilidad base, así que se aplica
// con estilo en línea sobre `animate-bounce`.
const retardos = ['0ms', '150ms', '300ms']
</script>

<template>
  <div class="flex justify-start" role="status" aria-label="El asistente está escribiendo">
    <div
      class="flex items-center gap-1.5 rounded-t-xl rounded-br-xl rounded-bl-none border border-gray-200 bg-gray-100 px-4 py-3"
    >
      <span
        v-for="retardo in retardos"
        :key="retardo"
        class="h-2 w-2 animate-bounce rounded-full bg-gray-400"
        :style="{ animationDelay: retardo }"
      ></span>
    </div>
  </div>
</template>
