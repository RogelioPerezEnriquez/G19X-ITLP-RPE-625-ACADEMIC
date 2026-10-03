import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './style.css'

const app = createApp(App)

app.use(createPinia())

// La app se monta recién cuando el store terminó de leer la sesión de
// Supabase: así el router ya conoce el estado de autenticación y los guards
// resuelven la primera navegación sin parpadeos ni redirecciones erróneas.
async function iniciarApp() {
  const authStore = useAuthStore()
  await authStore.inicializar()
  app.use(router)
  app.mount('#app')
}

iniciarApp()
