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
  clientOnboarding: vi.fn(),
  instances: vi.fn(),
  tokens: vi.fn(),
  alerts: vi.fn(),
  definitions: vi.fn(),
  subscription: vi.fn(),
  ledger: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: { refresh: vi.fn() } }))

import { installGuards, routes } from '@/router'
import { useAuthStore } from '@/stores/authStore'

const CLIENT: Client = {
  id: 'c1',
  code: 'SEO',
  name: 'SEO Group',
  nit: null,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  instances_total: 2,
  instances_online: 1,
  last_seen_at: null,
  oldest_version: null,
  identity_mode: 'pseudonym',
  config_locked: false,
  allow_local_cli: false,
  ai_policy: {
    allowed_providers: null,
    user_monthly_usd: null,
    provider_monthly_usd: {},
    user_overrides: {},
  },
  access_policy: {
    default_databases: null,
    user_databases: {},
    groups: [
      { id: 'g1', name: 'Soporte', members: ['u1', 'u2'], databases: [], user_monthly_usd: '12' },
      { id: 'g2', name: 'Ventas', members: [], databases: [], user_monthly_usd: null },
    ],
  },
}

const ALL = ['clients.read', 'clients.billing', 'clients.policy', 'tokens.manage', 'alerts.read']

async function mountAt(path: string, permissions: string[] = ALL) {
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
  const wrapper = mount(
    { template: '<RouterView />' },
    { global: { plugins: [router] }, attachTo: document.body },
  )
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  api.client.mockResolvedValue({ ...CLIENT })
  api.clientMetrics.mockResolvedValue({
    period: { start: '', end: '' },
    freshness: { seconds: 0, last_seen_at: null },
    totals: {},
    series: [],
    by_model: [],
    tools: [],
  })
  api.definitions.mockResolvedValue([])
  api.instances.mockResolvedValue([])
  api.clientDatabases.mockResolvedValue([])
  api.clientUsers.mockResolvedValue([])
  api.clientPeople.mockResolvedValue([])
  api.clientCounts.mockResolvedValue({ people: 0, open_alerts: 0 })
  api.clientOnboarding.mockResolvedValue({
    plan_loaded: true,
    policy_defined: true,
    ai_defined: true,
    token_created: true,
    instance_connected: true,
    report_received: true,
  })
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

describe('URLs anteriores a la reorganización', () => {
  it.each([
    ['suscripcion', '/clientes/c1/plan', ''],
    ['politica', '/clientes/c1/configuracion', '#instalaciones'],
    ['ia', '/clientes/c1/configuracion', '#ia'],
    ['acceso', '/clientes/c1/configuracion', '#acceso'],
    ['instancias', '/clientes/c1/operacion/instancias', ''],
    ['sucursales', '/clientes/c1/operacion/sucursales', ''],
    ['usuarios', '/clientes/c1/operacion/personas', ''],
  ])('/clientes/c1/%s redirige a su lugar nuevo', async (old, path, hash) => {
    const { router } = await mountAt(`/clientes/c1/${old}`)

    expect(router.currentRoute.value.path).toBe(path)
    expect(router.currentRoute.value.hash).toBe(hash)
  })

  it('una URL vieja sin permiso termina en el resumen del cliente', async () => {
    const { router } = await mountAt('/clientes/c1/politica', ['clients.read'])

    expect(router.currentRoute.value.path).toBe('/clientes/c1/resumen')
  })
})

describe('pestañas agrupadas', () => {
  it('quedan seis: Resumen, Plan, Configuración, Operación, Vinculación y Alertas', async () => {
    const { wrapper } = await mountAt('/clientes/c1/resumen')
    const labels = wrapper.findAll('.ui-tabs a').map((a) => a.text().replace(/\s*\d+$/, ''))

    expect(labels).toEqual([
      'Resumen',
      'Plan',
      'Configuración',
      'Operación',
      'Vinculación',
      'Alertas',
    ])
  })

  it('Operación queda activa en cualquiera de sus subsecciones', async () => {
    const { wrapper } = await mountAt('/clientes/c1/operacion/personas')

    expect(wrapper.get('.ui-tabs__tab--active').text()).toContain('Operación')
    expect(wrapper.get('[data-test="operation-personas"]').classes()).toContain(
      'segments__item--active',
    )
  })
})

describe('Configuración', () => {
  it('reúne Instalaciones, IA y Acceso con su navegación interna', async () => {
    const { wrapper } = await mountAt('/clientes/c1/configuracion')

    expect(wrapper.findAll('.config__link').map((a) => a.text())).toEqual([
      'Instalaciones',
      'IA',
      'Acceso',
    ])
    expect(wrapper.find('[data-test="ai-policy"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="access-policy"]').exists()).toBe(true)
    expect(wrapper.find('#config-instalaciones').exists()).toBe(true)
  })

  it('el ancla de la URL se desplaza hasta su sección y marca la navegación', async () => {
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    const { wrapper, router } = await mountAt('/clientes/c1/configuracion#acceso')

    expect(scroll).toHaveBeenCalled()
    expect(wrapper.get('[data-test="config-nav-acceso"]').classes()).toContain(
      'config__link--active',
    )

    await wrapper.get('[data-test="config-nav-ia"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.hash).toBe('#ia')
    expect(wrapper.get('[data-test="config-nav-ia"]').classes()).toContain('config__link--active')
  })

  it('la sección IA resume los topes de los grupos y enlaza a Acceso', async () => {
    const { wrapper, router } = await mountAt('/clientes/c1/configuracion#ia')
    const rows = wrapper.findAll('[data-test="group-cap"]').map((r) => r.text())

    expect(rows).toHaveLength(2)
    expect(rows[0]).toContain('Soporte')
    expect(rows[0]).toContain('12')
    expect(rows[1]).toContain('Sin tope')

    await wrapper.get('[data-test="group-caps-link"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.hash).toBe('#acceso')
  })

  it('exige el permiso de política', async () => {
    const { router } = await mountAt('/clientes/c1/configuracion', ['clients.read'])

    expect(router.currentRoute.value.path).toBe('/clientes/c1/resumen')
  })
})

describe('aviso al salir con cambios en varias secciones', () => {
  async function dirtyBoth() {
    const page = await mountAt('/clientes/c1/configuracion')
    await page.wrapper.get('[data-test="ai-user-cap"] input').setValue('5')
    await page.wrapper.get('[data-test="access-group-name"] input').setValue('Nuevo')
    await page.wrapper.get('[data-test="access-group-add"]').trigger('submit')
    await flushPromises()
    expect(page.wrapper.findAll('[data-test="unsaved-save"]')).toHaveLength(2)
    return page
  }

  it('pregunta una sola vez y deja salir si la persona acepta', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { router } = await dirtyBoth()

    await router.push('/clientes/c1/resumen')
    await flushPromises()

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/clientes/c1/resumen')
  })

  it('si la persona cancela, se queda en Configuración', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { router } = await dirtyBoth()

    await router.push('/clientes/c1/resumen')
    await flushPromises()

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/clientes/c1/configuracion')
  })

  it('con una sola sección sucia también avisa; limpia no molesta', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const clean = await mountAt('/clientes/c1/configuracion')
    await clean.router.push('/clientes/c1/resumen')
    await flushPromises()
    expect(confirm).not.toHaveBeenCalled()

    const dirty = await mountAt('/clientes/c1/configuracion')
    await dirty.wrapper.get('[data-test="ai-user-cap"] input').setValue('5')
    await dirty.router.push('/clientes/c1/resumen')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
  })

  it('cambiar de ancla dentro de Configuración no pregunta', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { router, wrapper } = await dirtyBoth()

    await wrapper.get('[data-test="config-nav-ia"]').trigger('click')
    await flushPromises()

    expect(confirm).not.toHaveBeenCalled()
    expect(router.currentRoute.value.hash).toBe('#ia')
  })
})
