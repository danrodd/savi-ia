import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { CLIENT_CONTEXT } from '@/lib/clientContext'
import type { AiPolicy, Client, ClientCounts, Permission } from '@/lib/types'

const api = vi.hoisted(() => ({
  clientDatabases: vi.fn(),
  clientUsers: vi.fn(),
  clientPeople: vi.fn(),
  instances: vi.fn(),
}))
const push = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('vue-router', async (original) => ({
  ...(await original<object>()),
  useRouter: () => ({ push }),
}))

import AiPolicyCard from '@/components/AiPolicyCard.vue'
import { useAuthStore } from '@/stores/authStore'
import ClientDatabasesTab from '@/views/client/ClientDatabasesTab.vue'
import ClientInstancesTab from '@/views/client/ClientInstancesTab.vue'
import ClientUsersTab from '@/views/client/ClientUsersTab.vue'

const POLICY: AiPolicy = {
  allowed_providers: null,
  user_monthly_usd: null,
  provider_monthly_usd: {},
  user_overrides: {},
}

function setRole(permissions: Permission[]): void {
  const auth = useAuthStore()
  auth.user = { id: 'u1', email: 'a@b.co', full_name: 'Ana', role: 'soporte', permissions }
  auth.accessToken = 'tok'
}

function context(instancesTotal: number, people = 0) {
  const client = ref({
    id: 'c1',
    instances_total: instancesTotal,
    identity_mode: 'pseudonym',
  } as Client)
  const counts = ref<ClientCounts | null>({ people, open_alerts: 0 })
  return {
    id: computed(() => 'c1'),
    client,
    reload: async () => undefined,
    counts,
    reloadCounts: async () => undefined,
  }
}

function mountTab(component: object, instancesTotal: number, people = 0) {
  return mount(component, {
    global: { provide: { [CLIENT_CONTEXT as symbol]: context(instancesTotal, people) } },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  api.clientDatabases.mockResolvedValue([])
  api.clientUsers.mockResolvedValue([])
  api.clientPeople.mockResolvedValue([])
  api.instances.mockResolvedValue([])
  setRole(['clients.read', 'tokens.manage'])
})

describe.each([
  ['Sucursales', ClientDatabasesTab, 'Todavía no informaron sucursales'],
  ['Personas', ClientUsersTab, 'Todavía no hay personas'],
  ['Instancias', ClientInstancesTab, 'Todavía no hay instalaciones vinculadas'],
])('vacío de %s', (_name, component, title) => {
  it('sin instalaciones explica por qué y lleva a Vinculación', async () => {
    const wrapper = mountTab(component, 0)
    await flushPromises()

    expect(wrapper.text()).toContain(title)
    await wrapper.get('[data-test="empty-cta"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/clientes/c1/vinculacion')
  })

  it('sin tokens.manage no ofrece un enlace prohibido: dice a quién pedirlo', async () => {
    setRole(['clients.read'])
    const wrapper = mountTab(component, 0)
    await flushPromises()

    expect(wrapper.find('[data-test="empty-cta"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="empty-role-hint"]').text()).toContain('Soporte')
  })
})

describe('con instalaciones que todavía no reportan', () => {
  it.each([
    ['Sucursales', ClientDatabasesTab],
    ['Personas', ClientUsersTab],
  ])('%s lleva a ver las instalaciones', async (_name, component) => {
    const wrapper = mountTab(component, 2)
    await flushPromises()

    expect(wrapper.text()).toContain('Hay instalaciones vinculadas')
    await wrapper.get('[data-test="empty-cta"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/clientes/c1/instancias')
  })
})

describe('Personas con historial', () => {
  it('si hubo personas pero ninguna en el período no manda a vincular', async () => {
    const wrapper = mountTab(ClientUsersTab, 1, 4)
    await flushPromises()

    expect(wrapper.text()).toContain('Sin personas activas en el período')
    expect(wrapper.find('[data-test="empty-cta"]').exists()).toBe(false)
  })
})

describe('excepciones de IA sin personas', () => {
  const mountAi = () => mount(AiPolicyCard, { props: { clientId: 'c1', policy: POLICY } })

  it('explica que la lista sale de quienes usaron SAVI y lleva a Vinculación', async () => {
    const wrapper = mountAi()
    await flushPromises()

    const empty = wrapper.get('[data-test="ai-no-people"]')
    expect(empty.text()).toContain('Todavía no hay personas para elegir')
    expect(wrapper.find('[data-test="ai-override-add"]').exists()).toBe(false)
    await empty.get('[data-test="empty-cta"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/clientes/c1/vinculacion')
  })

  it('con personas muestra el formulario de siempre', async () => {
    api.clientPeople.mockResolvedValue([
      {
        user_ref: 'a'.repeat(32),
        label: 'ANA',
        sessions: 1,
        last_session_at: '2026-10-01T00:00:00Z',
      },
    ])
    const wrapper = mountAi()
    await flushPromises()

    expect(wrapper.find('[data-test="ai-no-people"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="ai-override-add"]').exists()).toBe(true)
  })
})
