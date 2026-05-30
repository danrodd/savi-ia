import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/modules/auth/stores/authStore'

const ChatView = () => import('@/modules/chat/views/ChatView.vue')
const LoginView = () => import('@/modules/auth/views/LoginView.vue')
const UserProfileView = () => import('@/modules/auth/views/UserProfileView.vue')

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
  ],
})

/**
 * Guard global de autenticación.
 *
 * - Rutas con `meta.requiresAuth` requieren sesión: si no hay, redirige
 *   a `/login?next=<ruta>` para volver tras login.
 * - Rutas con `meta.hideForAuthed` (login) se evitan si ya hay sesión:
 *   se redirige a `/`.
 */
router.beforeEach((to, _from, next) => {
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
  next()
})

export default router
