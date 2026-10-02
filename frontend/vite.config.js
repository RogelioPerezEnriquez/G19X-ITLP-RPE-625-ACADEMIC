import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  // El .env con las variables VITE_* vive en la raíz del repositorio (es el
  // mismo que usa el backend). Vite solo carga los .env de su propio
  // directorio raíz, así que apuntamos envDir un nivel arriba. Vite expone
  // al cliente únicamente las variables con prefijo VITE_.
  envDir: '..',
})
