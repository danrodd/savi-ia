import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Instance, InstanceMetrics, Person, Usage } from '@/lib/types'

const api = vi.hoisted(() => ({
  instance: vi.fn(),
  instancePeople: vi.fn(),
  instanceMetrics: vi.fn(),
  heartbeats: vi.fn(),
  revokeInstance: vi.fn(),
  instanceAction: vi.fn(),
  definitions: vi.fn(),
  subscription: vi.fn(),
  ledger: vi.fn(),
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

import FiltersPanel from '@/components/FiltersPanel.vue'
import PersonLabel from '@/components/PersonLabel.vue'
import SubscriptionCard from '@/components/SubscriptionCard.vue'
import { useAuthStore } from '@/stores/authStore'
import InstanceDetailView from '@/views/InstanceDetailView.vue'

const INSTANCE = {
  id: 'i1',
  client_id: 'c1',
  client_code: 'AAA',
  client_name: 'Llantas Uno',
  name: 'SRV-UNO',
  deployment_mode: 'server',
  os: 'windows',
  agent_db_engine: 'postgresql',
  version: 'v1.5.0',
  commit: null,
  status: 'active',
  online: true,
  outdated: false,
  enrolled_at: '2026-11-01T00:00:00Z',
  last_seen_at: '2026-11-18T00:00:00Z',
  status_reason: null,
  fingerprint: null,
  clock_skew_seconds: null,
  rotation_requested_at: null,
  last_heartbeat: null,
} as Instance

const PEOPLE: Person[] = [
  {
    user_ref: 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6',
    number: 4,
    label: null,
    sessions: 3,
    last_session_at: '2026-11-17T00:00:00Z',
  },
]

const METRICS: InstanceMetrics = {
  period: { start: '2026-10-19T00:00:00Z', end: '2026-11-18T00:00:00Z' },
  totals: {
    turns: 120,
    cost_usd: '4.5',
    active_users: 3,
    error_rate: 0.025,
    turns_with_error: 3,
  } as Usage,
  series: [],
}

async function mountInstance(permissions: string[]) {
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
    routes: [
      { path: '/instancias/:id', component: InstanceDetailView },
      { path: '/:p(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/instancias/i1')
  const wrapper = mount(
    { template: '<RouterView />' },
    { global: { plugins: [router] }, attachTo: document.body },
  )
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  document.body.innerHTML = ''
  api.instance.mockResolvedValue(INSTANCE)
  api.instancePeople.mockResolvedValue(PEOPLE)
  api.instanceMetrics.mockResolvedValue(METRICS)
  api.heartbeats.mockResolvedValue({ items: [], next_cursor: null })
  api.definitions.mockResolvedValue([])
  api.revokeInstance.mockResolvedValue(INSTANCE)
})

describe('detalle de la instalación', () => {
  it('nombra a las personas por su número y muestra el uso propio', async () => {
    const wrapper = await mountInstance(['instances.read'])

    expect(api.instanceMetrics).toHaveBeenCalledWith('i1')
    expect(wrapper.get('[data-test="person-label"]').text()).toContain('Persona 4')
    expect(wrapper.text()).toContain('120')
    expect(wrapper.text()).toContain('3 de 120')
  })

  it('revocar está en "Más acciones" y pide escribir el nombre de la instalación', async () => {
    const wrapper = await mountInstance(['instances.read', 'instances.manage'])
    expect(wrapper.text()).not.toContain('Revocar instalación')

    await wrapper.get('[data-test="more-actions"]').trigger('click')
    await flushPromises()
    ;(document.querySelector('[data-test="action-revoke"]') as HTMLButtonElement).click()
    await flushPromises()

    const input = document.querySelector('[data-test="type-to-confirm"] input') as HTMLInputElement
    expect(document.body.textContent).toContain('Para continuar escriba SRV-UNO')
    const accept = document.querySelector('[data-test="confirm-accept"]') as HTMLButtonElement
    expect(accept.disabled).toBe(true)

    input.value = 'SRV-UNO'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    accept.click()
    await flushPromises()

    // El contrato del backend sigue siendo la palabra REVOCAR.
    expect(api.revokeInstance).toHaveBeenCalledWith('i1', 'REVOCAR')
  })
})

describe('persona', () => {
  it('copia el seudónimo completo', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const wrapper = mount(PersonLabel, { props: { userRef: 'abcdef1234567890', number: 2 } })

    expect(wrapper.text()).toContain('Persona 2')
    await wrapper.get('[data-test="person-copy"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('abcdef1234567890')
  })

  it('con identidad por usuario muestra el código y no ofrece copiar', () => {
    const wrapper = mount(PersonLabel, { props: { userRef: 'x', label: 'JPEREZ', number: 1 } })
    expect(wrapper.text()).toContain('JPEREZ')
    expect(wrapper.find('[data-test="person-copy"]').exists()).toBe(false)
  })
})

describe('plan', () => {
  it('los formularios arrancan plegados y se abren con sus botones', async () => {
    api.subscription.mockResolvedValue({
      plan_name: 'Pro',
      monthly_fee_usd: '120.00',
      max_users: 10,
      valid_until: '2026-12-31',
      notes: null,
      status: 'active',
      days_left: 40,
    })
    api.ledger.mockResolvedValue([])
    const wrapper = mount(SubscriptionCard, { props: { clientId: 'c1' } })
    await flushPromises()

    expect(wrapper.get('[data-test="plan-panel"]').attributes('style')).toContain('display: none')
    expect(wrapper.get('[data-test="entry-panel"]').attributes('style')).toContain('display: none')

    await wrapper.get('[data-test="plan-edit"]').trigger('click')
    expect(wrapper.get('[data-test="plan-panel"]').attributes('style') ?? '').not.toContain(
      'display: none',
    )
    expect(wrapper.get('[data-test="entry-panel"]').attributes('style')).toContain('display: none')
  })
})

describe('filtros', () => {
  it('el botón despliega los filtros y muestra cuántos están activos', async () => {
    const wrapper = mount(FiltersPanel, {
      props: { active: 2 },
      slots: { default: '<p>campos</p>' },
    })
    const toggle = wrapper.get('[data-test="filters-toggle"]')
    expect(toggle.text()).toContain('2')
    expect(toggle.attributes('aria-expanded')).toBe('false')

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.classes()).toContain('filters-panel--open')
  })
})
