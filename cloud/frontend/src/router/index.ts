import {
  createRouter,
  createWebHistory,
  type RouteComponent,
  type RouteRecordRaw,
  type Router,
} from 'vue-router'
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

/** Pestaña del detalle del cliente. El permiso lo exige también el backend: esto solo oculta. */
function clientTab(
  path: string,
  component: RouteComponent | (() => Promise<RouteComponent>),
  title: string,
  permission?: Permission,
): RouteRecordRaw {
  return {
    path,
    name: `client-${path}`,
    component,
    meta: { permission: permission ?? 'clients.read', title: `Cliente · ${title}` },
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
        // Cada pestaña del cliente tiene URL propia: se puede recargar o compartir.
        path: 'clientes/:id',
        component: () => import('@/views/ClientDetailView.vue'),
        meta: { permission: 'clients.read', title: 'Cliente' },
        children: [
          {
            path: '',
            name: 'client-detail',
            redirect: (to) => `/clientes/${to.params.id}/resumen`,
          },
          clientTab('resumen', () => import('@/views/client/ClientSummaryTab.vue'), 'Resumen'),
          clientTab(
            'suscripcion',
            () => import('@/views/client/ClientSubscriptionTab.vue'),
            'Suscripción',
            'clients.billing',
          ),
          clientTab(
            'politica',
            () => import('@/views/client/ClientPolicyTab.vue'),
            'Política',
            'clients.policy',
          ),
          clientTab('ia', () => import('@/views/client/ClientAiTab.vue'), 'IA', 'clients.policy'),
          clientTab(
            'acceso',
            () => import('@/views/client/ClientAccessTab.vue'),
            'Acceso',
            'clients.policy',
          ),
          clientTab(
            'instancias',
            () => import('@/views/client/ClientInstancesTab.vue'),
            'Instancias',
          ),
          clientTab(
            'sucursales',
            () => import('@/views/client/ClientDatabasesTab.vue'),
            'Sucursales',
          ),
          clientTab('usuarios', () => import('@/views/client/ClientUsersTab.vue'), 'Usuarios'),
          clientTab(
            'vinculacion',
            () => import('@/views/client/ClientTokensTab.vue'),
            'Vinculación',
            'tokens.manage',
          ),
          clientTab('alertas', () => import('@/views/client/ClientAlertsTab.vue'), 'Alertas'),
        ],
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

/** Acceso por sesión y permisos, y título de la pestaña del navegador. */
export function installGuards(router: Router): void {
  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    await auth.restore()

    if (to.meta.public) {
      return auth.isAuthenticated ? { name: 'overview' } : true
    }
    if (!auth.isAuthenticated) {
      return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : undefined }
    }
    // Los permisos se exigen en toda la cadena: una pestaña hereda el de su pantalla.
    const denied = to.matched.some((record) => {
      const required = record.meta.permission
      return required !== undefined && !auth.can(required)
    })
    if (denied) {
      // En una pestaña sin permiso, mejor el resumen del mismo cliente que la portada.
      const clientId = to.params.id
      if (to.matched.length > 2 && typeof clientId === 'string' && auth.can('clients.read')) {
        return `/clientes/${clientId}/resumen`
      }
      return { name: 'overview' }
    }
    return true
  })

  router.afterEach((to) => {
    document.title = to.meta.title ? `${to.meta.title} · SAVI Cloud` : 'SAVI Cloud'
  })
}

const router = createRouter({ history: createWebHistory(), routes })
installGuards(router)

export default router
