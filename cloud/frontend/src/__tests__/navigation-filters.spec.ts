import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { AuditEntry, Instance } from '@/lib/types'

const api = vi.hoisted(() => ({
  alertSummary: vi.fn(),
  alerts: vi.fn(),
  alertRules: vi.fn(),
  clients: vi.fn(),
  instances: vi.fn(),
  overview: vi.fn(),
  audit: vi.fn(),
  definitions: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))

import AppLayout from '@/components/AppLayout.vue'
import { resetOpenAlertsForTests } from '@/composables/useOpenAlerts'
import { resetRuleTitlesForTests } from '@/lib/ruleTitles'
import { useAuthStore } from '@/stores/authStore'
import AlertsView from '@/views/AlertsView.vue'
import AuditView from '@/views/AuditView.vue'
import InstancesView from '@/views/InstancesView.vue'
import OverviewView from '@/views/OverviewView.vue'

const instance = (id: string, over: Partial<Instance> = {}): Instance =>
  ({
    id,
    client_id: 'c1',
    client_code: 'SEO',
    client_name: 'SEO Group',
    name: `Sede ${id}`,
    version: '1.4.2',
    status: 'active',
    online: true,
    outdated: false,
    last_seen_at: null,
    ...over,
  }) as Instance

async function mountAt(component: object, path: string, permissions: string[]) {
  const auth = useAuthStore()
  auth.user = {
    id: 'u',
    email: 'a@b.co',
    full_name: 'Ana',
    role: 'admin',
    permissions: permissions as never,
  }
  auth.accessToken = 'tok'
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div>home</div>' } },
      { path: '/:p(.*)*', component: { template: '<div>otra</div>' } },
    ],
  })
  await router.push(path)
  const wrapper = mount(component, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

const field = (wrapper: ReturnType<typeof mount>, name: string) =>
  wrapper.get(`[data-test="${name}"] input, [data-test="${name}"] select`)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  resetOpenAlertsForTests()
  resetRuleTitlesForTests()
  document.body.innerHTML = ''
  api.alertRules.mockResolvedValue([])
  api.definitions.mockResolvedValue([])
  api.alertSummary.mockResolvedValue({ open: 4, acknowledged: 1 })
  api.alerts.mockResolvedValue([])
  api.clients.mockResolvedValue({
    items: [
      { id: 'c1', name: 'SEO Group' },
      { id: 'c2', name: 'Farmacias X' },
    ],
    total: 2,
  })
  api.instances.mockResolvedValue([
    instance('i1'),
    instance('i2', { version: '1.3.0', name: 'Bodega' }),
  ])
})

describe('menú lateral', () => {
  it('muestra las alertas abiertas junto a "Alertas" si hay permiso', async () => {
    const { wrapper } = await mountAt(AppLayout, '/', ['alerts.read', 'overview.read'])

    expect(api.alertSummary).toHaveBeenCalled()
    expect(wrapper.get('[data-test="nav-badge-alertas"]').text()).toBe('4')
  })

  it('sin permiso para ver alertas no pide ni muestra el contador', async () => {
    const { wrapper } = await mountAt(AppLayout, '/', ['overview.read'])

    expect(api.alertSummary).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="nav-badge-alertas"]').exists()).toBe(false)
  })

  it('con cero alertas no dibuja el contador y al navegar se relee', async () => {
    api.alertSummary.mockResolvedValue({ open: 0, acknowledged: 0 })
    const { wrapper, router } = await mountAt(AppLayout, '/', ['alerts.read'])
    expect(wrapper.find('[data-test="nav-badge-alertas"]').exists()).toBe(false)

    api.alertSummary.mockResolvedValue({ open: 120, acknowledged: 0 })
    await router.push('/clientes')
    await flushPromises()

    expect(api.alertSummary).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-test="nav-badge-alertas"]').text()).toBe('99+')
  })
})

describe('instancias', () => {
  it('lee los filtros de la URL y los manda al backend', async () => {
    await mountAt(InstancesView, '/instancias?version=1.4.2&client=c2&status=active', [
      'instances.read',
    ])

    expect(api.instances).toHaveBeenLastCalledWith(
      expect.objectContaining({ version: '1.4.2', client_id: 'c2', status: 'active' }),
    )
  })

  it('cambiar un filtro actualiza la URL y recarga', async () => {
    const { wrapper, router } = await mountAt(InstancesView, '/instancias', ['instances.read'])

    await field(wrapper, 'instances-client').setValue('c2')
    await flushPromises()
    expect(router.currentRoute.value.query.client).toBe('c2')
    expect(api.instances).toHaveBeenLastCalledWith(expect.objectContaining({ client_id: 'c2' }))

    await field(wrapper, 'instances-version').setValue('1.4.2')
    await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({ client: 'c2', version: '1.4.2' })
    expect(api.instances).toHaveBeenLastCalledWith(
      expect.objectContaining({ client_id: 'c2', version: '1.4.2' }),
    )
  })

  it('la búsqueda filtra por nombre sin volver a pedir y queda en la URL', async () => {
    const { wrapper, router } = await mountAt(InstancesView, '/instancias', ['instances.read'])
    const calls = api.instances.mock.calls.length

    await field(wrapper, 'instances-search').setValue('bodega')
    await flushPromises()

    expect(wrapper.text()).toContain('Bodega')
    expect(wrapper.text()).not.toContain('Sede i1')
    expect(router.currentRoute.value.query.q).toBe('bodega')
    expect(api.instances.mock.calls.length).toBe(calls)
  })

  it('con la búsqueda en la URL arranca ya filtrado', async () => {
    const { wrapper } = await mountAt(InstancesView, '/instancias?q=zzz', ['instances.read'])

    expect(wrapper.text()).toContain('No hay instancias con esos filtros')
  })
})

describe('resumen', () => {
  it('cada versión instalada enlaza a las instancias de esa versión', async () => {
    api.overview.mockResolvedValue({
      clients: { active: 1, suspended: 0 },
      instances: { online: 1, offline: 0, suspended: 0, revoked: 0 },
      period: { start: '', end: '' },
      freshness: { seconds: 0, last_seen_at: null },
      usage: { turns: 0, active_users: 0, cost_usd: '0' },
      trend: [],
      providers: [],
      versions: [
        { version: '1.4.2', instances: 3 },
        { version: null, instances: 1 },
      ],
      open_alerts: { info: 0, warning: 0, critical: 0 },
    })
    const { wrapper } = await mountAt(OverviewView, '/', ['overview.read'])
    const links = wrapper.findAll('[data-test="version-link"]')

    expect(links).toHaveLength(1)
    expect(links[0]?.attributes('href')).toBe('/instancias?version=1.4.2')
    expect(wrapper.text()).toContain('Sin informar')
  })
})

describe('alertas', () => {
  it('el filtro por cliente va a la URL y al backend; "todas" quita el estado', async () => {
    const { wrapper, router } = await mountAt(AlertsView, '/alertas', ['alerts.read'])
    expect(api.alerts).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'open' }))

    await field(wrapper, 'alerts-client').setValue('c2')
    await flushPromises()
    expect(router.currentRoute.value.query.client).toBe('c2')
    expect(api.alerts).toHaveBeenLastCalledWith(expect.objectContaining({ client_id: 'c2' }))

    await field(wrapper, 'alerts-status').setValue('')
    await flushPromises()
    expect(router.currentRoute.value.query.status).toBe('todas')
    expect(api.alerts).toHaveBeenLastCalledWith(expect.objectContaining({ status: undefined }))
  })

  it('un enlace con ?client= llega filtrado', async () => {
    await mountAt(AlertsView, '/alertas?client=c1', ['alerts.read'])

    expect(api.alerts).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'open', client_id: 'c1' }),
    )
  })
})

describe('auditoría', () => {
  const entry = (id: string, type: string, target: string): AuditEntry => ({
    id,
    occurred_at: '2026-10-01T00:00:00Z',
    actor_email: 'ana@seo.example',
    action: 'x.y',
    target_type: type,
    target_id: target,
    before: null,
    after: null,
    ip: null,
  })

  beforeEach(() => {
    api.audit.mockResolvedValue({
      items: [entry('e1', 'client', 'c1'), entry('e2', 'alert', 'a1b2c3d4e5f6')],
      next_cursor: null,
    })
  })

  it('muestra el nombre del cliente y enlaza; lo no resoluble cae a tipo + id corto', async () => {
    const { wrapper } = await mountAt(AuditView, '/auditoria', ['audit.read'])

    expect(wrapper.text()).toContain('Cliente SEO Group')
    expect(wrapper.text()).toContain('Alerta a1b2c3d4…')
    const links = wrapper.findAll('[data-test="target-link"]')
    expect(links.length).toBeGreaterThan(0)
    expect(links[0]?.attributes('href')).toBe('/clientes/c1')
  })

  it('pulsar un objeto filtra por él con un chip que se quita', async () => {
    const { wrapper, router } = await mountAt(AuditView, '/auditoria', ['audit.read'])

    await wrapper.findAll('[data-test="target-filter"]')[0]?.trigger('click')
    await flushPromises()
    expect(api.audit).toHaveBeenLastCalledWith(expect.objectContaining({ target: 'c1' }))
    expect(router.currentRoute.value.query.target).toBe('c1')
    expect(wrapper.get('[data-test="target-chip"]').text()).toContain('Cliente SEO Group')

    await wrapper.get('[data-test="target-chip-remove"]').trigger('click')
    await flushPromises()
    expect(api.audit).toHaveBeenLastCalledWith(expect.objectContaining({ target: undefined }))
    expect(wrapper.find('[data-test="target-chip"]').exists()).toBe(false)
  })

  it('un enlace con ?target= arranca filtrado', async () => {
    await mountAt(AuditView, '/auditoria?target=c1', ['audit.read'])

    expect(api.audit).toHaveBeenLastCalledWith(expect.objectContaining({ target: 'c1' }))
  })
})
