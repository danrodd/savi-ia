import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Alert, Client, Instance, Overview, Usage } from '@/lib/types'

const api = vi.hoisted(() => ({
  overview: vi.fn(),
  alerts: vi.fn(),
  alertRules: vi.fn(),
  definitions: vi.fn(),
  clients: vi.fn(),
  instances: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))

import { resetRuleTitlesForTests } from '@/lib/ruleTitles'
import { useAuthStore } from '@/stores/authStore'
import ClientsView from '@/views/ClientsView.vue'
import InstancesView from '@/views/InstancesView.vue'
import OverviewView from '@/views/OverviewView.vue'

function usage(turns: number, cost: string, users: number): Usage {
  return { turns, cost_usd: cost, active_users: users } as Usage
}

const OVERVIEW: Overview = {
  clients: { active: 4, suspended: 0 },
  instances: { online: 3, offline: 1, suspended: 0, revoked: 0 },
  period: { start: '2026-10-19T00:00:00Z', end: '2026-11-18T00:00:00Z' },
  freshness: { seconds: 30, last_seen_at: null },
  usage: usage(150, '30.00', 12),
  previous_usage: usage(100, '30.00', 0),
  trend: [],
  top_clients: [
    {
      client_id: 'c1',
      code: 'AAA',
      name: 'Llantas Uno',
      turns: 90,
      active_users: 6,
      cost_usd: '18',
    },
    {
      client_id: 'c2',
      code: 'BBB',
      name: 'Farmacia Dos',
      turns: 40,
      active_users: 4,
      cost_usd: '8',
    },
    { client_id: 'c3', code: 'CCC', name: 'Agro Tres', turns: 15, active_users: 1, cost_usd: '3' },
    {
      client_id: 'c4',
      code: 'DDD',
      name: 'Resto Cuatro',
      turns: 5,
      active_users: 1,
      cost_usd: '1',
    },
  ],
  trend_by_client: [
    { day: '2026-11-17', client_id: 'c1', turns: 90 },
    { day: '2026-11-17', client_id: 'c2', turns: 40 },
    { day: '2026-11-17', client_id: 'c3', turns: 15 },
    { day: '2026-11-17', client_id: null, turns: 5 },
  ],
  providers: [],
  versions: [],
  open_alerts: { info: 0, warning: 1, critical: 1 },
}

function alert(id: string, severity: Alert['severity'], opened: string): Alert {
  return {
    id,
    rule_code: 'instance_offline',
    severity,
    status: 'open',
    client_id: 'c1',
    client_name: 'Llantas Uno',
    instance_id: null,
    details: {},
    opened_at: opened,
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
  }
}

async function mountView(component: object, permissions: string[]) {
  const auth = useAuthStore()
  auth.user = {
    id: 's1',
    email: 'a@seo.example',
    full_name: 'Ana',
    role: 'admin',
    permissions: permissions as never,
  }
  auth.accessToken = 'tok'
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/')
  const wrapper = mount(component, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  resetRuleTitlesForTests()
  document.body.innerHTML = ''
  api.overview.mockResolvedValue(OVERVIEW)
  api.alertRules.mockResolvedValue([{ code: 'instance_offline', title: 'Instancia sin conexión' }])
  api.definitions.mockResolvedValue([])
})

describe('resumen', () => {
  it('lista primero lo crítico en "Requiere atención", con su cliente', async () => {
    api.alerts.mockResolvedValue([
      alert('a1', 'warning', '2026-11-17T10:00:00Z'),
      alert('a2', 'critical', '2026-11-10T10:00:00Z'),
    ])
    const wrapper = await mountView(OverviewView, ['overview.read', 'alerts.read'])

    expect(api.alerts).toHaveBeenCalledWith({ status: 'open' })
    const items = wrapper.findAll('[data-test="attention"] .item')
    expect(items).toHaveLength(2)
    expect(items[0]?.classes()).toContain('item--critical')
    expect(items[0]?.text()).toContain('Instancia sin conexión')
    expect(items[0]?.find('a').attributes('href')).toBe('/clientes/c1/alertas')
  })

  it('dice que no hay nada pendiente cuando no hay alertas abiertas', async () => {
    api.alerts.mockResolvedValue([])
    const wrapper = await mountView(OverviewView, ['overview.read', 'alerts.read'])
    expect(wrapper.get('[data-test="attention-empty"]').text()).toContain('Nada pendiente')
  })

  it('no pide las alertas a quien no puede verlas', async () => {
    const wrapper = await mountView(OverviewView, ['overview.read'])
    expect(api.alerts).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="attention"]').exists()).toBe(false)
  })

  it('muestra la variación solo cuando hay con qué comparar', async () => {
    api.alerts.mockResolvedValue([])
    const wrapper = await mountView(OverviewView, ['overview.read', 'alerts.read'])
    const changes = wrapper.findAll('[data-test="kpi-change"]').map((c) => c.text())
    // Turnos 100 → 150; costo igual; personas sin base (0 en el periodo anterior).
    expect(changes).toEqual([
      expect.stringContaining('+50 %'),
      expect.stringContaining('Sin cambio'),
    ])
    expect(wrapper.text()).toContain('Sin datos del periodo anterior')
  })

  it('apila los tres clientes principales y suma el resto en Otros', async () => {
    api.alerts.mockResolvedValue([])
    const wrapper = await mountView(OverviewView, ['overview.read', 'alerts.read'])
    const legend = wrapper.findAll('.legend li').map((li) => li.text())
    expect(legend).toEqual(['Llantas Uno', 'Farmacia Dos', 'Agro Tres', 'Otros'])
    expect(wrapper.text()).toContain('Clientes con más uso')
    expect(wrapper.text()).toContain('Resto Cuatro')
  })
})

const CLIENT: Client = {
  id: 'c1',
  code: 'AAA',
  name: 'Llantas Uno',
  nit: null,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  instances_total: 1,
  instances_online: 0,
  instances_waiting: 1,
  instances_offline: 0,
  last_seen_at: null,
  oldest_version: null,
  identity_mode: 'pseudonym',
  config_locked: false,
  allow_local_cli: false,
  ai_policy: {} as Client['ai_policy'],
  access_policy: {} as Client['access_policy'],
  turns_30d: 1234,
  active_users_30d: 7,
  cost_30d_usd: '12.5',
  health: 'warning',
  plan: { name: 'Empresarial', max_users: 20, valid_until: '2026-11-20', status: 'expiring' },
}

describe('clientes', () => {
  it('ordena por atención y muestra plan, consumo e instalaciones en palabras', async () => {
    api.clients.mockResolvedValue({ items: [CLIENT], total: 1 })
    const wrapper = await mountView(ClientsView, ['clients.read', 'clients.billing'])

    expect(api.clients).toHaveBeenCalledWith(expect.objectContaining({ sort: 'attention' }))
    const row = wrapper.get('tbody tr')
    expect(row.text()).toContain('Empresarial')
    expect(row.text()).toContain('Vence pronto')
    expect(row.text()).toContain('7 / 20')
    expect(row.text()).toContain('1.234')
    expect(row.text()).toContain('Esperando primera conexión')
    expect(row.get('[data-test="health-dot"]').attributes('aria-label')).toBe('Requiere atención')
  })

  it('sin permiso de facturación no muestra la columna de plan', async () => {
    api.clients.mockResolvedValue({ items: [{ ...CLIENT, plan: null }], total: 1 })
    const wrapper = await mountView(ClientsView, ['clients.read'])
    expect(wrapper.findAll('th').map((th) => th.text())).not.toContain('Plan')
  })
})

describe('instancias', () => {
  it('muestra el modo, los turnos y desde cuándo espera la primera conexión', async () => {
    const instance = {
      id: 'i1',
      client_id: 'c1',
      client_code: 'AAA',
      client_name: 'Llantas Uno',
      name: 'Caja 1',
      deployment_mode: 'desktop',
      os: 'windows',
      agent_db_engine: 'sqlite',
      version: 'v1.5.0',
      commit: null,
      status: 'active',
      online: false,
      outdated: false,
      enrolled_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
      last_seen_at: null,
      turns_30d: 42,
    } as unknown as Instance
    api.instances.mockResolvedValue([instance])
    const wrapper = await mountView(InstancesView, ['instances.read'])

    const row = wrapper.get('tbody tr')
    expect(row.get('[data-test="instance-mode"]').attributes('aria-label')).toBe(
      'Equipo de escritorio',
    )
    expect(row.text()).toContain('42')
    expect(row.text()).toContain('Vinculada hace 3 h')
  })
})
