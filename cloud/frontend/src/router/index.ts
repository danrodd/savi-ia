import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import type { Permission } from '@/lib/types'
import { useAuthStore } from '@/stores/authStore'

declare module 'vue-router' {
  interface RouteMeta {
    /** Permiso que habilita la pantalla. El backend igual lo exige: esto solo oculta. */
    permission?: Permission
    public?: boolean
    title?: string
  }
}

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true, title: 'Ingresar' },
  },
  {
    path: '/',
    component: () => import('@/components/AppLayout.vue'),
    children: [
      {
        path: '',
        name: 'overview',
        component: () => import('@/views/OverviewView.vue'),
        meta: { permission: 'overview.read', title: 'Resumen' },
      },
      {
        path: 'clientes',
        name: 'clients',
        component: () => import('@/views/ClientsView.vue'),
        meta: { permission: 'clients.read', title: 'Clientes' },
      },
      {
        path: 'clientes/:id',
        name: 'client-detail',
        component: () => import('@/views/ClientDetailView.vue'),
        meta: { permission: 'clients.read', title: 'Cliente' },
      },
      {
        path: 'instancias',
        name: 'instances',
        component: () => import('@/views/InstancesView.vue'),
        meta: { permission: 'instances.read', title: 'Instancias' },
      },
      {
        path: 'instancias/:id',
        name: 'instance-detail',
        component: () => import('@/views/InstanceDetailView.vue'),
        meta: { permission: 'instances.read', title: 'Instancia' },
      },
      {
        path: 'alertas',
        name: 'alerts',
        component: () => import('@/views/AlertsView.vue'),
        meta: { permission: 'alerts.read', title: 'Alertas' },
      },
      {
        path: 'configuracion/alertas',
        name: 'alert-rules',
        component: () => import('@/views/AlertRulesView.vue'),
        meta: { permission: 'alerts.configure', title: 'Reglas de alerta' },
      },
      {
        path: 'staff',
        name: 'staff',
        component: () => import('@/views/StaffView.vue'),
        meta: { permission: 'staff.manage', title: 'Equipo' },
      },
      {
        path: 'auditoria',
        name: 'audit',
        component: () => import('@/views/AuditView.vue'),
        meta: { permission: 'audit.read', title: 'Auditoría' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restore()

  if (to.meta.public) {
    return auth.isAuthenticated ? { name: 'overview' } : true
  }
  if (!auth.isAuthenticated) {
    return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : undefined }
  }
  const required = to.meta.permission
  if (required && !auth.can(required)) return { name: 'overview' }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · SAVI Cloud` : 'SAVI Cloud'
})

export default router
