import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import RecomendacionesView from '../views/RecomendacionesView.vue'
import RecomendacionDetalleView from '../views/RecomendacionDetalleView.vue'
import ProveedoresView from '../views/ProveedoresView.vue'
import ChatView from '../views/ChatView.vue'
import KpisView from '../views/KpisView.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true },
    },
    {
      path: '/recomendaciones',
      name: 'recomendaciones',
      component: RecomendacionesView,
      meta: { requiresAuth: true },
    },
    {
      path: '/proveedores',
      name: 'proveedores',
      component: ProveedoresView,
      meta: { requiresAuth: true },
    },
    {
      path: '/chat',
      name: 'chat',
      component: ChatView,
      meta: { requiresAuth: true },
    },
    {
      path: '/kpis',
      name: 'kpis',
      component: KpisView,
      meta: { requiresAuth: true },
    },
    {
      path: '/recomendaciones/:productoId',
      name: 'recomendacionDetalle',
      component: RecomendacionDetalleView,
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  // Si la inicialización del store todavía está en curso (por ejemplo, la
  // primera navegación disparada antes de que `main.js` termine de esperarla),
  // se espera acá: los guards nunca deciden con estado incompleto.
  if (authStore.cargando) {
    await authStore.inicializar()
  }

  if (to.meta.requiresAuth && !authStore.estaAutenticado) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    return { name: 'home' }
  }

  // Con sesión activa, las pantallas de acceso no tienen sentido.
  if (authStore.estaAutenticado && (to.name === 'login' || to.name === 'register')) {
    return { name: 'home' }
  }

  return true
})

export default router
