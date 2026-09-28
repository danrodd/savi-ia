import { createRouter, createWebHistory } from 'vue-router'

import { ENV } from '@/lib/env'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import { type ModuleCode, usePermisosStore } from '@/modules/permisos'
import { isAdminRouteDenied } from './adminGuard'
import { shouldShowLanding } from './landingRedirect'

const ChatView = () => import('@/modules/chat/views/ChatView.vue')
const LoginView = () => import('@/modules/auth/views/LoginView.vue')
const UserProfileView = () => import('@/modules/auth/views/UserProfileView.vue')
const SinAccesoView = () => import('@/modules/permisos/views/SinAccesoView.vue')
const AdminLayout = () => import('@/modules/admin/views/AdminLayout.vue')
const ErpDatabasesView = () => import('@/modules/admin/views/ErpDatabasesView.vue')
const AdminUsageView = () => import('@/modules/admin/views/AdminUsageView.vue')
const LlmProvidersView = () => import('@/modules/admin/views/LlmProvidersView.vue')
const CompanyKnowledgeView = () => import('@/modules/admin/views/CompanyKnowledgeView.vue')
const NotFoundView = () => import('@/components/NotFoundView.vue')
const LandingView = () => import('@/modules/landing/views/LandingView.vue')

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    hideForAuthed?: boolean
    /** Si está presente, el guard exige que el usuario tenga este módulo. */
    requireModule?: ModuleCode
    requiresAdmin?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // Landing pública: solo existe donde se compiló con VITE_LANDING_ENABLED.
    // En el servidor de un cliente la ruta ni se registra (cae en 404).
    ...(ENV.LANDING_ENABLED
      ? [
          {
            path: '/inicio',
            name: 'landing',
            component: LandingView,
            meta: { requiresAuth: false },
          },
        ]
      : []),
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
      // Vista compartida de una conversación — misma UI que /c/:id pero
      // con banner identificador. Si la conversación es del usuario
      // actual queda totalmente editable; si pertenece a otro usuario
      // se renderiza en modo solo lectura. La detección de propiedad
      // la hace ChatView vs authStore.user.id. Hoy el endpoint backend
      // scopea por user_id (404 para no-dueño); cuando se habilite
      // acceso público basta con habilitarlo en backend — el frontend
      // ya está listo para read-only.
      path: '/share/:id',
      name: 'shared-conversation',
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
      // Enlace histórico: el consumo propio vive en /perfil y el global en admin.
      path: '/consumo',
      name: 'usage',
      redirect: () =>
        useAuthStore().user?.is_admin ? { name: 'admin-usage' } : { name: 'profile' },
    },
    {
      path: '/admin',
      component: AdminLayout,
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        { path: '', name: 'admin', redirect: { name: 'admin-databases' } },
        { path: 'bases-datos', name: 'admin-databases', component: ErpDatabasesView },
        { path: 'proveedores-ia', name: 'admin-llm-providers', component: LlmProvidersView },
        {
          path: 'conocimiento',
          name: 'admin-company-knowledge',
          component: CompanyKnowledgeView,
        },
        { path: 'consumo', name: 'admin-usage', component: AdminUsageView },
      ],
    },
    {
      path: '/sin-acceso',
      name: 'no-access',
      component: SinAccesoView,
      meta: { requiresAuth: true },
    },
    {
      // Catch-all. Sin esto una URL desconocida no matchea ninguna ruta y el
      // router no renderiza nada: pantalla en blanco. Va último a propósito —
      // vue-router respeta el orden de declaración para rutas equivalentes.
      // Sin `requiresAuth`: mandar al login por un typo confunde más de lo que
      // ayuda, y la vista no muestra ningún dato.
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundView,
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
 * 4. Rutas con `meta.requiresAdmin` (en la ruta o en un padre) exigen
 *    `is_admin`; si no, redirige a `/`.
 */
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()
  if (shouldShowLanding(to.name, authStore.isAuthenticated, ENV.LANDING_ENABLED)) {
    next({ name: 'landing' })
    return
  }
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
  if (isAdminRouteDenied(to, authStore.user)) {
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
