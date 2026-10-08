<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConfiguracionStore } from '../stores/configuracion'

const router = useRouter()
const authStore = useAuthStore()
const configuracionStore = useConfiguracionStore()

// Formato español para mostrar el valor persistido (p. ej. 0,5). Los inputs
// usan el formato estándar de HTML5 number (punto decimal).
const formateadorNumero = new Intl.NumberFormat('es-ES', {
  maximumFractionDigits: 4,
})

// Parámetros cuyo valor representa un porcentaje o puntaje en escala 0-100.
// Nota: eoq_min_pct / eoq_max_pct se excluyen porque su rango válido supera
// el 100 % (el valor por defecto de eoq_max_pct es 110).
const PARAMETROS_0_A_100 = new Set([
  'abc_clase_a_pct',
  'abc_clase_b_pct',
  'ahorro_neto_min_pct',
  'score_proveedor_confiable',
  'score_proveedor_riesgoso',
])

// Parámetros que deben ser estrictamente positivos.
const PARAMETROS_POSITIVOS = new Set([
  'demanda_ventana_default',
  'eoq_min_pct',
  'eoq_max_pct',
])

function valorDe(nombre) {
  const parametro = configuracionStore.parametros.find(
    (p) => p.nombre_parametro === nombre
  )
  return parametro ? Number(parametro.valor) : null
}

// Lista de mensajes de validación; si está vacía, el formulario es válido.
const erroresValidacion = computed(() => {
  const errores = []

  for (const parametro of configuracionStore.parametros) {
    const crudo = parametro.valor
    const numero = Number(crudo)
    const nombre = parametro.nombre_parametro

    if (crudo === '' || crudo === null || crudo === undefined || !Number.isFinite(numero)) {
      errores.push(`El valor de "${nombre}" debe ser numérico.`)
      continue
    }

    if (PARAMETROS_0_A_100.has(nombre) && (numero < 0 || numero > 100)) {
      errores.push(`El valor de "${nombre}" debe estar entre 0 y 100.`)
    }

    if (PARAMETROS_POSITIVOS.has(nombre) && numero <= 0) {
      errores.push(`El valor de "${nombre}" debe ser mayor que 0.`)
    }
  }

  const claseA = valorDe('abc_clase_a_pct')
  const claseB = valorDe('abc_clase_b_pct')
  if (
    Number.isFinite(claseA) &&
    Number.isFinite(claseB) &&
    claseA >= claseB
  ) {
    errores.push('"abc_clase_a_pct" debe ser menor que "abc_clase_b_pct".')
  }

  return errores
})

const puedeGuardar = computed(
  () =>
    configuracionStore.hayCambios &&
    erroresValidacion.value.length === 0 &&
    !configuracionStore.guardando
)

function fueModificado(parametro) {
  return Number(parametro.valor) !== Number(parametro.valorOriginal)
}

async function guardar() {
  if (!puedeGuardar.value) return
  await configuracionStore.actualizarTodos()
}

function cancelar() {
  configuracionStore.descartarCambios()
}

onMounted(() => {
  // El guard del router ya bloquea a los no-admins; esta verificación cubre
  // el caso de una sesión que pierde el rol con la vista ya montada.
  if (!authStore.isAdmin) {
    router.replace({ name: 'home' })
    return
  }
  configuracionStore.listar()
})
</script>

<template>
  <section class="space-y-6">
    <div>
      <h1 class="text-2xl font-semibold text-gray-900">
        Configuración de parámetros
      </h1>
      <p class="mt-1 text-sm text-gray-600">
        Modifica los umbrales del sistema. Los cambios se aplican en la
        próxima ejecución del motor.
      </p>
    </div>

    <div
      v-if="configuracionStore.cargando"
      class="flex items-center justify-center gap-3 rounded-lg bg-white p-8 text-gray-600 shadow-sm"
    >
      <span
        class="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"
        aria-hidden="true"
      ></span>
      Cargando...
    </div>

    <div
      v-else-if="configuracionStore.error && configuracionStore.parametros.length === 0"
      class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
    >
      <p>{{ configuracionStore.error }}</p>
      <button
        type="button"
        class="mt-2 font-medium underline"
        @click="configuracionStore.listar()"
      >
        Reintentar
      </button>
    </div>

    <form
      v-else
      class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:p-6"
      @submit.prevent="guardar"
    >
      <div class="divide-y divide-gray-100">
        <div
          v-for="parametro in configuracionStore.parametros"
          :key="parametro.nombre_parametro"
          class="flex flex-col gap-2 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-6"
        >
          <div class="min-w-0">
            <label
              :for="`param-${parametro.nombre_parametro}`"
              class="block font-mono text-sm font-medium text-gray-900"
            >
              {{ parametro.nombre_parametro }}
            </label>
            <p class="mt-0.5 text-xs text-gray-500">
              {{ parametro.descripcion }}
            </p>
            <p
              v-if="fueModificado(parametro)"
              class="mt-0.5 text-xs text-blue-600"
            >
              Valor actual: {{ formateadorNumero.format(parametro.valorOriginal) }}
            </p>
          </div>

          <input
            :id="`param-${parametro.nombre_parametro}`"
            v-model="parametro.valor"
            type="number"
            step="any"
            required
            class="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 sm:w-40"
            :class="{ 'border-blue-400 bg-blue-50': fueModificado(parametro) }"
          />
        </div>
      </div>

      <div
        v-if="erroresValidacion.length > 0"
        class="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
      >
        <p class="font-medium">Revisa los siguientes errores:</p>
        <ul class="mt-1 list-inside list-disc space-y-0.5">
          <li v-for="mensaje in erroresValidacion" :key="mensaje">
            {{ mensaje }}
          </li>
        </ul>
      </div>

      <div
        v-if="configuracionStore.error && configuracionStore.parametros.length > 0"
        class="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
      >
        {{ configuracionStore.error }}
      </div>

      <div
        v-if="configuracionStore.exito"
        class="mt-4 rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-700"
      >
        {{ configuracionStore.exito }}
      </div>

      <div class="mt-6 flex items-center justify-end gap-3">
        <span v-if="configuracionStore.guardando" class="text-sm text-gray-600">
          Guardando...
        </span>
        <button
          type="button"
          class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!configuracionStore.hayCambios || configuracionStore.guardando"
          @click="cancelar"
        >
          Cancelar
        </button>
        <button
          type="submit"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!puedeGuardar"
        >
          Guardar cambios
        </button>
      </div>
    </form>
  </section>
</template>
