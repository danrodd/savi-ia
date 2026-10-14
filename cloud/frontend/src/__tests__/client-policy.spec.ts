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
  setClientAiPolicy: vi.fn(),
  setClientAccessPolicy: vi.fn(),
  suspendClient: vi.fn(),
  activateClient: vi.fn(),
  definitions: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))

import { useAuthStore } from '@/stores/authStore'
import ClientDetailView from '@/views/ClientDetailView.vue'

const DB_1 = '7a1f3c52-9d4e-4b6a-8c0d-1e2f3a4b5c6d'
const DB_2 = '11111111-2222-4333-8444-555555555555'

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
  allow_local_cli: false,
  ai_policy: {
    allowed_providers: null,
    user_monthly_usd: null,
    provider_monthly_usd: {},
    user_overrides: {},
  },
  access_policy: { default_databases: null, user_databases: {}, groups: [] },
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
  api.setClientAiPolicy.mockResolvedValue({ ...CLIENT })
  api.setClientAccessPolicy.mockResolvedValue({ ...CLIENT })
  api.clientDatabases.mockResolvedValue([
    {
      database_ref: DB_1,
      code: 'NORTE',
      name: 'Sede Norte',
      is_active: true,
      is_usable: true,
      credentials_unreadable: false,
      last_connection_ok_at: null,
      snapshot_date: '2026-10-01',
    },
    {
      database_ref: DB_2,
      code: 'SUR',
      name: 'Sede Sur',
      is_active: true,
      is_usable: true,
      credentials_unreadable: false,
      last_connection_ok_at: null,
      snapshot_date: '2026-10-01',
    },
  ])
  api.clientUsers.mockResolvedValue([
    {
      user_ref: 'a'.repeat(32),
      label: 'JPEREZ',
      turns: 3,
      cost_usd: '1.2',
      last_used_at: '2026-10-01T00:00:00Z',
      databases_used: 1,
    },
  ])
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

  it('permitir el CLI de Claude pide confirmación y manda solo ese campo', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    await wrapper.get('[data-test="toggle-cli"]').trigger('click')
    expect(api.setClientPolicy).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('con su propia cuenta')

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Permitir CLI de Claude' && b.classes().includes('btn-danger'))
      ?.trigger('click')
    await flushPromises()

    expect(api.setClientPolicy).toHaveBeenCalledWith('c1', { allow_local_cli: true })
  })

  it('un cliente ya bloqueado ofrece permitir la configuración', async () => {
    api.client.mockResolvedValue({ ...CLIENT, config_locked: true })
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    expect(wrapper.get('[data-test="toggle-lock"]').text()).toBe('Permitir configuración')
    expect(wrapper.text()).toContain('Bloqueada')
  })
})

describe('IA: proveedores y topes del cliente', () => {
  async function open() {
    return mountView(['clients.read', 'clients.policy'])
  }

  async function save(wrapper: Awaited<ReturnType<typeof open>>) {
    await wrapper.get('[data-test="ai-save"]').trigger('click')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Guardar límites')
      ?.trigger('click')
    await flushPromises()
  }

  it('solo la ve quien tiene el permiso', async () => {
    const without = await mountView(['clients.read'])
    expect(without.find('[data-test="ai-policy"]').exists()).toBe(false)
  })

  it('guarda el tope por persona y manda todos los proveedores como null', async () => {
    const wrapper = await open()

    await wrapper.get('[data-test="ai-user-cap"]').setValue('5')
    await save(wrapper)

    expect(api.setClientAiPolicy).toHaveBeenCalledWith('c1', {
      allowed_providers: null,
      user_monthly_usd: '5',
      provider_monthly_usd: {},
      user_overrides: {},
    })
  })

  it('desmarcar un proveedor y fijar su tope viaja en el cuerpo', async () => {
    const wrapper = await open()

    await wrapper.get('[data-test="ai-provider-openai"]').setValue(false)
    await wrapper.get('[data-test="ai-provider-cap-gemini"]').setValue('50')
    await save(wrapper)

    expect(api.setClientAiPolicy).toHaveBeenCalledWith('c1', {
      allowed_providers: ['claude', 'gemini'],
      user_monthly_usd: null,
      provider_monthly_usd: { gemini: '50' },
      user_overrides: {},
    })
  })

  it('agrega una excepción por persona usando su código de usuario', async () => {
    const wrapper = await open()

    await wrapper.get('[data-test="ai-override-person"]').setValue('a'.repeat(32))
    await wrapper.get('[data-test="ai-override-amount"]').setValue('20')
    await wrapper.get('[data-test="ai-override-add"]').trigger('click')

    expect(wrapper.get('[data-test="ai-override"]').text()).toContain('JPEREZ')
    await save(wrapper)
    expect(api.setClientAiPolicy).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({ user_overrides: { ['a'.repeat(32)]: '20' } }),
    )
  })

  it('rechaza montos inválidos sin llamar al API', async () => {
    const wrapper = await open()

    await wrapper.get('[data-test="ai-user-cap"]').setValue('-5')
    await wrapper.get('[data-test="ai-save"]').trigger('click')

    expect(wrapper.get('[data-test="ai-error"]').text()).toContain('USD')
    expect(api.setClientAiPolicy).not.toHaveBeenCalled()
  })

  it('no deja guardar sin ningún proveedor habilitado', async () => {
    const wrapper = await open()

    for (const key of ['claude', 'gemini', 'openai']) {
      await wrapper.get(`[data-test="ai-provider-${key}"]`).setValue(false)
    }
    await wrapper.get('[data-test="ai-save"]').trigger('click')

    expect(wrapper.get('[data-test="ai-error"]').text()).toContain('al menos un proveedor')
    expect(api.setClientAiPolicy).not.toHaveBeenCalled()
  })

  it('avisa que Gemini y OpenAI necesitan precios cuando hay un tope', async () => {
    const wrapper = await open()
    expect(wrapper.find('[data-test="ai-price-warning"]').exists()).toBe(false)

    await wrapper.get('[data-test="ai-user-cap"]').setValue('5')

    expect(wrapper.get('[data-test="ai-price-warning"]').text()).toContain('precios')
  })
})

describe('bases por persona', () => {
  async function save(wrapper: Awaited<ReturnType<typeof mountView>>) {
    await wrapper.get('[data-test="access-save"]').trigger('click')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Guardar reglas')
      ?.trigger('click')
    await flushPromises()
  }

  it('solo la ve quien tiene el permiso', async () => {
    const without = await mountView(['clients.read'])
    expect(without.find('[data-test="access-policy"]').exists()).toBe(false)
  })

  it('sin restricción general manda null', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    await save(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: null,
      user_databases: {},
      groups: [],
    })
  })

  it('limitar por defecto manda solo las bases marcadas', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    await wrapper.get('[data-test="access-limit-default"]').setValue(true)
    await wrapper.get(`[data-test="access-default-${DB_1}"]`).setValue(true)
    await save(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: [DB_1],
      user_databases: {},
      groups: [],
    })
  })

  it('una regla por persona con bases marcadas', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])
    const ref = 'a'.repeat(32)

    await wrapper.get('[data-test="access-rule-person"]').setValue(ref)
    await wrapper.get('[data-test="access-rule-add"]').trigger('click')
    expect(wrapper.get('[data-test="access-rule"]').text()).toContain('JPEREZ')
    await wrapper.get(`[data-test="access-rule-${ref}-${DB_2}"]`).setValue(true)
    await save(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: null,
      user_databases: { [ref]: [DB_2] },
      groups: [],
    })
  })

  it('avisa cuando una regla queda sin ninguna base', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    await wrapper.get('[data-test="access-rule-person"]').setValue('a'.repeat(32))
    await wrapper.get('[data-test="access-rule-add"]').trigger('click')

    expect(wrapper.get('[data-test="access-rule-empty"]').text()).toContain('no podrán consultar')
  })

  it('arma un grupo con personas y bases', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])
    const ref = 'a'.repeat(32)

    await wrapper.get('[data-test="access-group-name"]').setValue('Soporte norte')
    await wrapper.get('[data-test="access-group-add"]').trigger('click')
    expect(wrapper.get('[data-test="access-group"]').text()).toContain('Soporte norte')
    await wrapper.get(`[data-test="access-group-Soporte norte-person-${ref}"]`).setValue(true)
    await wrapper.get(`[data-test="access-group-Soporte norte-db-${DB_1}"]`).setValue(true)
    await save(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: null,
      user_databases: {},
      groups: [{ id: null, name: 'Soporte norte', members: [ref], databases: [DB_1] }],
    })
  })

  it('no permite dos grupos con el mismo nombre', async () => {
    const wrapper = await mountView(['clients.read', 'clients.policy'])

    await wrapper.get('[data-test="access-group-name"]').setValue('Norte')
    await wrapper.get('[data-test="access-group-add"]').trigger('click')
    await wrapper.get('[data-test="access-group-name"]').setValue('norte')
    await wrapper.get('[data-test="access-group-add"]').trigger('click')

    expect(wrapper.findAll('[data-test="access-group"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="access-error"]').text()).toContain('ese nombre')
  })
})
