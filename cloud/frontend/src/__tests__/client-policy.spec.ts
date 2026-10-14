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
  instances: vi.fn(),
  tokens: vi.fn(),
  alerts: vi.fn(),
  setClientPolicy: vi.fn(),
  suspendClient: vi.fn(),
  activateClient: vi.fn(),
  definitions: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))

import { useAuthStore } from '@/stores/authStore'
import ClientDetailView from '@/views/ClientDetailView.vue'

const CLIENT: Client = {
  id: 'c1',
  code: 'SEO',
  name: 'SEO Group',
  nit: null,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  instances_total: 5,
  instances_online: 5,
  last_seen_at: null,
  oldest_version: 'v1.2.0',
  identity_mode: 'pseudonym',
  config_locked: false,
}

async function mountView(permissions: string[]) {
  const auth = useAuthStore()
  auth.user = {
    id: 'u1',
    email: 'a@b.co',
    full_name: 'Ana',
    role: 'admin',
    permissions: permissions as never,
  }
  auth.accessToken = 'tok'
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/clientes/:id', component: ClientDetailView }],
  })
  await router.push('/clientes/c1')
  const wrapper = mount(ClientDetailView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  api.client.mockResolvedValue({ ...CLIENT })
  api.clientMetrics.mockResolvedValue({
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
  })
  api.definitions.mockResolvedValue([])
  api.setClientPolicy.mockResolvedValue({ ...CLIENT, config_locked: true })
})

describe('política de las instalaciones del cliente', () => {
  it('solo la ve quien tiene el permiso', async () => {
    const without = await mountView(['clients.read'])
    expect(without.find('[data-test="client-policy"]').exists()).toBe(false)

    setActivePinia(createPinia())
    const withPermission = await mountView(['clients.read', 'clients.policy'])
    expect(withPermission.find('[data-test="client-policy"]').exists()).toBe(true)
  })

  it('bloquear la configuración pide confirmación y recién ahí llama al API', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    await wrapper.get('[data-test="toggle-lock"]').trigger('click')
    expect(api.setClientPolicy).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Dejar las instalaciones solo con el chat')

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Bloquear configuración' && b.classes().includes('btn-danger'))
      ?.trigger('click')
    await flushPromises()

    expect(api.setClientPolicy).toHaveBeenCalledWith('c1', { config_locked: true })
  })

  it('identificar a las personas advierte que es solo para la organización interna', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    await wrapper.get('[data-test="toggle-identity"]').trigger('click')

    expect(wrapper.text()).toContain('organización interna')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Identificar personas' && b.classes().includes('btn-danger'))
      ?.trigger('click')
    await flushPromises()
    expect(api.setClientPolicy).toHaveBeenCalledWith('c1', { identity_mode: 'named' })
  })

  it('un cliente ya bloqueado ofrece permitir la configuración', async () => {
    api.client.mockResolvedValue({ ...CLIENT, config_locked: true })
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    expect(wrapper.get('[data-test="toggle-lock"]').text()).toBe('Permitir configuración')
    expect(wrapper.text()).toContain('Bloqueada')
  })
})
