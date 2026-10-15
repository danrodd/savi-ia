import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Client } from '@/lib/types'

const api = vi.hoisted(() => ({
  client: vi.fn(),
  clientMetrics: vi.fn(),
  clientDatabases: vi.fn(),
  clientUsers: vi.fn(),
  clientPeople: vi.fn(),
  clientCounts: vi.fn(),
  acknowledgeAlert: vi.fn(),
  resolveAlert: vi.fn(),
  instances: vi.fn(),
  tokens: vi.fn(),
  alerts: vi.fn(),
  alertRules: vi.fn(),
  definitions: vi.fn(),
  subscription: vi.fn(),
  ledger: vi.fn(),
  updateClient: vi.fn(),
  suspendClient: vi.fn(),
  activateClient: vi.fn(),
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: { refresh: vi.fn() } }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

import { installGuards, routes } from '@/router'
import { useAuthStore } from '@/stores/authStore'

const CLIENT: Client = {
  id: 'c1',
  code: 'SEO',
  name: 'SEO Group',
  nit: '900123',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  instances_total: 2,
  instances_online: 1,
  last_seen_at: null,
  oldest_version: 'v1.2.0',
  identity_mode: 'pseudonym',
  config_locked: false,
  allow_local_cli: false,
  ai_policy: {
    allowed_providers: null,
    user_monthly_usd: null,
    provider_monthly_usd: {},
    user_overrides: {},
  },
  access_policy: { default_databases: null, user_databases: {}, groups: [] },
}

const EMPTY_METRICS = {
  period: { start: '', end: '' },
  freshness: { seconds: 0, last_seen_at: null },
  totals: {
    turns: 0,
    conversations: 0,
    active_users: 0,
    entering_users: 0,
    adoption: null,
    tokens: 0,
    cost_usd: '0',
    cost_per_active_user: null,
    turns_without_price: 0,
    turns_with_error: 0,
    turns_interrupted: 0,
    turns_truncated: 0,
    error_rate: null,
    latency_p50_ms: null,
    latency_p90_ms: null,
    free_queries: 0,
    free_queries_failed: 0,
  },
  series: [],
  by_model: [],
  by_database: [],
  tools: [],
  finish_reasons: {},
}

async function mountAt(path: string, permissions: string[]) {
  const auth = useAuthStore()
  auth.user = {
    id: 'u1',
    email: 'a@b.co',
    full_name: 'Ana',
    role: 'admin',
    permissions: permissions as never,
  }
  auth.accessToken = 'tok'
  auth.restored = true
  const router = createRouter({ history: createMemoryHistory(), routes })
  installGuards(router)
  await router.push(path)
  const App = { template: '<RouterView />' }
  const wrapper = mount(App, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  document.body.innerHTML = ''
  api.client.mockResolvedValue({ ...CLIENT })
  api.clientMetrics.mockResolvedValue(EMPTY_METRICS)
  api.definitions.mockResolvedValue([])
  api.alertRules.mockResolvedValue([])
  api.instances.mockResolvedValue([])
  api.clientDatabases.mockResolvedValue([])
  api.clientUsers.mockResolvedValue([])
  api.clientPeople.mockResolvedValue([])
  api.clientCounts.mockResolvedValue({ people: 7, open_alerts: 3 })
  api.alerts.mockResolvedValue([])
  api.tokens.mockResolvedValue([])
  api.subscription.mockResolvedValue({
    plan_name: null,
    monthly_fee_usd: null,
    max_users: null,
    valid_until: null,
    notes: null,
    status: 'none',
    days_left: null,
  })
  api.ledger.mockResolvedValue([])
})

describe('detalle del cliente', () => {
  it('entrar al cliente abre la pestaña Resumen con su URL', async () => {
    const { wrapper, router } = await mountAt('/clientes/c1', ['clients.read'])

    expect(router.currentRoute.value.path).toBe('/clientes/c1/resumen')
    expect(wrapper.get('h1').text()).toBe('SEO Group')
    expect(wrapper.text()).toContain('Últimos 30 días')
  })

  it('solo muestra las pestañas que permite el rol', async () => {
    const { wrapper } = await mountAt('/clientes/c1', ['clients.read'])
    const labels = wrapper.findAll('.ui-tabs a').map((a) => a.text().replace(/\s*\d+$/, ''))

    expect(labels).toEqual(['Resumen', 'Instancias', 'Sucursales', 'Usuarios', 'Alertas'])
  })

  it('con todos los permisos aparecen suscripción, política, IA, acceso y vinculación', async () => {
    const { wrapper } = await mountAt('/clientes/c1', [
      'clients.read',
      'clients.billing',
      'clients.policy',
      'tokens.manage',
    ])
    const labels = wrapper.findAll('.ui-tabs a').map((a) => a.text().replace(/\s*\d+$/, ''))

    expect(labels).toEqual([
      'Resumen',
      'Suscripción',
      'Política',
      'IA',
      'Acceso',
      'Instancias',
      'Sucursales',
      'Usuarios',
      'Vinculación',
      'Alertas',
    ])
  })

  it('las pestañas muestran cuántas instancias, personas y alertas abiertas hay', async () => {
    const { wrapper } = await mountAt('/clientes/c1', ['clients.read', 'alerts.read'])
    const count = (label: string) => {
      const tab = wrapper.findAll('.ui-tabs a').find((a) => a.text().startsWith(label))
      const badge = tab?.find('.ui-tabs__count')
      return badge?.exists() ? badge.text() : undefined
    }

    expect(api.clientCounts).toHaveBeenCalledWith('c1')
    expect(count('Instancias')).toBe('2')
    expect(count('Usuarios')).toBe('7')
    expect(count('Alertas')).toBe('3')
    expect(count('Resumen')).toBeUndefined()
  })

  it('sin permiso para ver alertas la pestaña no muestra su contador', async () => {
    const { wrapper } = await mountAt('/clientes/c1', ['clients.read'])
    const tab = wrapper.findAll('.ui-tabs a').find((a) => a.text().startsWith('Alertas'))

    expect(tab?.find('.ui-tabs__count').exists()).toBe(false)
  })

  it('en la pestaña Usuarios se busca por etiqueta o seudónimo', async () => {
    api.clientUsers.mockResolvedValue([
      {
        user_ref: 'aaaa1111bbbb',
        label: 'JPEREZ',
        turns: 3,
        cost_usd: '1',
        last_used_at: '2026-10-01T00:00:00Z',
        databases_used: 1,
      },
      {
        user_ref: 'cccc2222dddd',
        label: null,
        turns: 2,
        cost_usd: '1',
        last_used_at: '2026-10-01T00:00:00Z',
        databases_used: 1,
      },
    ])
    const { wrapper } = await mountAt('/clientes/c1/usuarios', ['clients.read'])
    const input = wrapper.get('[data-test="users-search"] input')
    const rows = () => wrapper.findAll('tbody tr').length

    expect(rows()).toBe(2)
    await input.setValue('jperez')
    expect(rows()).toBe(1)
    await input.setValue('cccc2222')
    expect(wrapper.text()).toContain('cccc2222')
    expect(wrapper.text()).not.toContain('JPEREZ')
    await input.setValue('zzz')
    expect(wrapper.text()).toContain('Ninguna persona coincide')
  })

  it('la pestaña Alertas permite reconocer y resolver con permiso de gestión', async () => {
    const alert = {
      id: 'a1',
      rule_code: 'subscription_due',
      severity: 'critical',
      status: 'open',
      client_id: 'c1',
      instance_id: null,
      details: {},
      opened_at: '2026-10-01T00:00:00Z',
      acknowledged_at: null,
      acknowledged_by: null,
      resolved_at: null,
      resolved_by: null,
      resolution_note: null,
    }
    api.alerts.mockResolvedValue([alert])
    api.acknowledgeAlert.mockResolvedValue({ ...alert, status: 'acknowledged' })
    api.resolveAlert.mockResolvedValue({ ...alert, status: 'resolved' })
    const { wrapper } = await mountAt('/clientes/c1/alertas', ['clients.read', 'alerts.manage'])
    const button = (text: string) => wrapper.findAll('button').find((b) => b.text() === text)

    await button('Reconocer')?.trigger('click')
    await flushPromises()
    expect(api.acknowledgeAlert).toHaveBeenCalledWith('a1')
    expect(api.alerts).toHaveBeenCalledTimes(2)
    expect(api.clientCounts).toHaveBeenCalledTimes(2)

    await button('Resolver')?.trigger('click')
    await flushPromises()
    await wrapper.get('textarea').setValue('  Listo ')
    await wrapper.get('[data-test="resolve-confirm"]').trigger('click')
    await flushPromises()
    expect(api.resolveAlert).toHaveBeenCalledWith('a1', 'Listo')
  })

  it('la pestaña Alertas sin permiso de gestión no ofrece acciones', async () => {
    api.alerts.mockResolvedValue([
      {
        id: 'a1',
        rule_code: 'x',
        severity: 'info',
        status: 'open',
        client_id: 'c1',
        instance_id: null,
        details: {},
        opened_at: '2026-10-01T00:00:00Z',
        acknowledged_at: null,
        acknowledged_by: null,
        resolved_at: null,
        resolved_by: null,
        resolution_note: null,
      },
    ])
    const { wrapper } = await mountAt('/clientes/c1/alertas', ['clients.read'])

    expect(wrapper.findAll('button').some((b) => b.text() === 'Reconocer')).toBe(false)
  })

  it('una pestaña sin permiso por URL directa vuelve al resumen del cliente', async () => {
    const { router } = await mountAt('/clientes/c1/suscripcion', ['clients.read'])

    expect(router.currentRoute.value.path).toBe('/clientes/c1/resumen')
  })

  it('cada pestaña se abre por su URL', async () => {
    const { wrapper } = await mountAt('/clientes/c1/ia', ['clients.read', 'clients.policy'])

    expect(wrapper.find('[data-test="ai-policy"]').exists()).toBe(true)
    expect(wrapper.find('.ui-tabs__tab--active').text()).toBe('IA')
  })

  it('editar el cliente manda nombre y NIT y recarga', async () => {
    api.updateClient.mockResolvedValue({ ...CLIENT, name: 'SEO Group S.A.S.' })
    const { wrapper } = await mountAt('/clientes/c1', ['clients.read', 'clients.write'])

    await wrapper.get('[data-test="client-edit"]').trigger('click')
    await flushPromises()
    const name = document.querySelector<HTMLInputElement>('[data-test="client-name"] input')
    expect(name?.value).toBe('SEO Group')
    if (name) {
      name.value = 'SEO Group S.A.S.'
      name.dispatchEvent(new Event('input'))
    }
    document.querySelector<HTMLFormElement>('#client-form')?.dispatchEvent(new Event('submit'))
    await flushPromises()

    expect(api.updateClient).toHaveBeenCalledWith('c1', { name: 'SEO Group S.A.S.', nit: '900123' })
    expect(toast.success).toHaveBeenCalledWith('Cliente actualizado')
    expect(api.client).toHaveBeenCalledTimes(2)
  })

  it('suspender pide confirmación y avisa', async () => {
    api.suspendClient.mockResolvedValue(undefined)
    const { wrapper } = await mountAt('/clientes/c1', ['clients.read', 'clients.suspend'])

    await wrapper.get('[data-test="client-suspend"]').trigger('click')
    await flushPromises()
    expect(api.suspendClient).not.toHaveBeenCalled()
    document.querySelector<HTMLButtonElement>('[data-test="confirm-accept"]')?.click()
    await flushPromises()

    expect(api.suspendClient).toHaveBeenCalledWith('c1')
    expect(toast.success).toHaveBeenCalledWith('Cliente suspendido')
  })

  it('sin permiso de escritura no ofrece editar ni suspender', async () => {
    const { wrapper } = await mountAt('/clientes/c1', ['clients.read'])

    expect(wrapper.find('[data-test="client-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="client-suspend"]').exists()).toBe(false)
  })
})
