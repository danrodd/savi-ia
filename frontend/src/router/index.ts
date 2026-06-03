import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/modules/auth/stores/authStore'
import { type ModuleCode, usePermisosStore } from '@/modules/permisos'

const ChatView = () => import('@/modules/chat/views/ChatView.vue')
const LoginView = () => import('@/modules/auth/views/LoginView.vue')
const UserProfileView = () => import('@/modules/auth/views/UserProfileView.vue')
const UsageView = () => import('@/modules/usage/views/UsageView.vue')
const SinAccesoView = () => import('@/modules/permisos/views/SinAccesoView.vue')

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    hideForAuthed?: boolean
    /** Si está presente, el guard exige que el usuario tenga este módulo. */
    requireModule?: ModuleCode
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresAuth: false, hideForAuthed: true },
    },
    {
      path: '/',
      name: 'home',
      component: ChatView,
      meta: { requiresAuth: true },
    },
    {
      path: '/c/:id',
      name: 'conversation',
      component: ChatView,
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/perfil',
      name: 'profile',
      component: UserProfileView,
      meta: { requiresAuth: true },
    },
    {
      path: '/consumo',
      name: 'usage',
      component: UsageView,
      meta: { requiresAuth: true },
    },
    {
      path: '/sin-acceso',
      name: 'no-access',
      component: SinAccesoView,
      meta: { requiresAuth: true },
    },
  ],
})

/**
 * Guard global.
 *
 * Orden:
 * 1. Rutas con `meta.requiresAuth` requieren sesión: si no hay, redirige
 *    a `/login?next=<ruta>` para volver tras login.
 * 2. Rutas con `meta.hideForAuthed` (login) se evitan si ya hay sesión:
 *    se redirige a `/`.
 * 3. Rutas con `meta.requireModule` exigen acceso al módulo. Si el store
 *    aún no cargó el bootstrap, espera. Si el usuario no lo tiene,
 *    redirige a `/sin-acceso?modulo=<CODE>`.
 */
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({
      name: 'login',
      query: { next: to.fullPath !== '/login' ? to.fullPath : undefined },
    })
    return
  }
  if (to.meta.hideForAuthed && authStore.isAuthenticated) {
    next({ name: 'home' })
    return
  }

  const requiredModule = to.meta.requireModule
  if (requiredModule && authStore.isAuthenticated) {
    const permisos = usePermisosStore()
    if (!permisos.loaded) {
      await permisos.cargarBootstrap()
    }
    if (!permisos.puede(requiredModule)) {
      next({ name: 'no-access', query: { modulo: requiredModule } })
      return
    }
  }

  next()
})

export default router
