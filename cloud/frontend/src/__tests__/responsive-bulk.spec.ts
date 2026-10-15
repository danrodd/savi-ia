import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Alert, Client, Instance } from '@/lib/types'

const api = vi.hoisted(() => ({
  alertSummary: vi.fn(),
  alerts: vi.fn(),
  alertRules: vi.fn(),
  acknowledgeAlerts: vi.fn(),
  resolveAlerts: vi.fn(),
  clients: vi.fn(),
  instances: vi.fn(),
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

import { openAlerts, resetOpenAlertsForTests } from '@/composables/useOpenAlerts'
import { resetRuleTitlesForTests } from '@/lib/ruleTitles'
import { useAuthStore } from '@/stores/authStore'
import AlertsView from '@/views/AlertsView.vue'
import ClientsView from '@/views/ClientsView.vue'
import InstancesView from '@/views/InstancesView.vue'

/** Ancho simulado de la ventana: `matchMedia` contesta según él. */
let viewport = 1280

function installMatchMedia(): void {
  window.matchMedia = ((query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query)
    return {
      matches: max ? viewport <= Number(max[1]) : false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    }
  }) as typeof window.matchMedia
}

const alert = (id: string, status: Alert['status'], rule = 'instance_offline'): Alert => ({
  id,
  rule_code: rule,
  severity: 'warning',
  status,
  client_id: 'c1',
  client_name: 'SEO Group',
  instance_id: null,
  details: {},
  opened_at: '2026-10-01T00:00:00Z',
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolved_by: null,
  resolution_note: null,
})

const instance = (id: string): Instance =>
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
  }) as Instance

const client = (id: string): Client =>
  ({
    id,
    code: id.toUpperCase(),
    name: `Cliente ${id}`,
    status: 'active',
    instances_total: 2,
    instances_online: 1,
    last_seen_at: null,
    oldest_version: 'v1.0.0',
  }) as Client

async function mountView(component: object, permissions: string[]) {
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
    routes: [{ path: '/:p(.*)*', component: { template: '<div>otra</div>' } }],
  })
  await router.push('/')
  const wrapper = mount(component, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  resetOpenAlertsForTests()
  resetRuleTitlesForTests()
  document.body.innerHTML = ''
  viewport = 1280
  installMatchMedia()
  api.alertRules.mockResolvedValue([])
  api.alertSummary.mockResolvedValue({ open: 2, acknowledged: 1 })
  api.clients.mockResolvedValue({ items: [client('c1'), client('c2')], total: 2 })
  api.instances.mockResolvedValue([instance('i1'), instance('i2')])
  api.alerts.mockResolvedValue([
    alert('a1', 'open'),
    alert('a2', 'open', 'clock_skew'),
    alert('a3', 'acknowledged'),
    alert('a4', 'resolved'),
  ])
})

afterEach(() => {
  // @ts-expect-error: se retira el simulador para no afectar a otros archivos.
  window.matchMedia = undefined
})

describe.each([
  ['Clientes', ClientsView, ['clients.read'], 2],
  ['Instancias', InstancesView, ['instances.read'], 2],
  ['Alertas', AlertsView, ['alerts.read'], 4],
])('%s en pantallas angostas', (_name, view, permissions, rows) => {
  it('muestra tarjetas por debajo de 720px, sin tabla que se corte', async () => {
    viewport = 390
    const wrapper = await mountView(view, permissions)

    expect(wrapper.findAll('[data-test="table-card"]')).toHaveLength(rows)
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('conserva la tabla en pantallas anchas', async () => {
    viewport = 1280
    const wrapper = await mountView(view, permissions)

    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.find('[data-test="table-card"]').exists()).toBe(false)
  })
})

describe('tarjetas', () => {
  it('cada campo lleva su etiqueta y la fila sigue siendo accionable', async () => {
    viewport = 390
    const wrapper = await mountView(ClientsView, ['clients.read'])
    const card = wrapper.get('[data-test="table-card"]')

    expect(card.text()).toContain('Cliente c1')
    expect(card.text()).toContain('Última actividad')
    expect(card.text()).toContain('Versión más antigua')
    expect(card.attributes('tabindex')).toBe('0')
  })

  it('los vacíos se muestran también como tarjeta', async () => {
    viewport = 390
    api.instances.mockResolvedValue([])
    const wrapper = await mountView(InstancesView, ['instances.read'])

    expect(wrapper.find('[data-test="table-card"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Todavía no hay instancias vinculadas')
  })
})

describe('acciones masivas en Alertas', () => {
  const pick = (wrapper: ReturnType<typeof mount>, index: number) =>
    wrapper.findAll('[data-test="alert-select"]')[index]

  it('sin permiso de gestión no hay casillas ni barra', async () => {
    const wrapper = await mountView(AlertsView, ['alerts.read'])

    expect(wrapper.find('[data-test="alerts-bulk"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="alert-select"]').exists()).toBe(false)
  })

  it('solo las alertas gestionables tienen casilla (las resueltas no)', async () => {
    const wrapper = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    expect(wrapper.findAll('[data-test="alert-select"]')).toHaveLength(3)
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('Ninguna seleccionada')
    expect(wrapper.get('[data-test="alerts-bulk-ack"]').attributes('disabled')).toBeDefined()
  })

  it('seleccionar todo (visibles) marca las gestionables y se puede deshacer', async () => {
    const wrapper = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])
    const all = wrapper.get('[data-test="alerts-select-all"] input')

    await all.setValue(true)
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('3 seleccionadas')
    expect(
      wrapper
        .findAll<HTMLInputElement>('[data-test="alert-select"]')
        .every((box) => box.element.checked),
    ).toBe(true)

    await pick(wrapper, 0)?.setValue(false)
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('2 seleccionadas')
    expect((all.element as HTMLInputElement).checked).toBe(false)

    // Con una selección parcial, la casilla general vuelve a seleccionar todo; otra vez, limpia.
    await all.setValue(true)
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('3 seleccionadas')
    await all.setValue(false)
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('Ninguna seleccionada')
  })

  it('reconocer manda una sola petición con las abiertas, avisa con conteos y refresca el menú', async () => {
    api.acknowledgeAlerts.mockResolvedValue({ changed: 2, skipped: 0 })
    const wrapper = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])
    api.alertSummary.mockResolvedValue({ open: 0, acknowledged: 3 })

    await wrapper.get('[data-test="alerts-select-all"] input').setValue(true)
    await wrapper.get('[data-test="alerts-bulk-ack"]').trigger('click')
    await flushPromises()

    // La reconocida (a3) no se manda: solo aplica a las abiertas.
    expect(api.acknowledgeAlerts).toHaveBeenCalledTimes(1)
    expect(api.acknowledgeAlerts).toHaveBeenCalledWith(['a1', 'a2'])
    expect(toast.success).toHaveBeenCalledWith('2 alertas reconocidas', { description: undefined })
    expect(api.alerts).toHaveBeenCalledTimes(2) // recarga la lista
    expect(openAlerts.value).toBe(0) // y el contador del menú
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('Ninguna seleccionada')
  })

  it('el aviso cuenta también las omitidas', async () => {
    api.acknowledgeAlerts.mockResolvedValue({ changed: 1, skipped: 1 })
    const wrapper = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    await pick(wrapper, 0)?.setValue(true)
    await pick(wrapper, 1)?.setValue(true)
    await wrapper.get('[data-test="alerts-bulk-ack"]').trigger('click')
    await flushPromises()

    expect(toast.success).toHaveBeenCalledWith('1 alerta reconocida', {
      description: '1 alerta se omitieron porque ya no estaban pendientes.',
    })
  })

  it('resolver pide la misma nota que una sola y manda todas juntas', async () => {
    api.resolveAlerts.mockResolvedValue({ changed: 3, skipped: 0 })
    const wrapper = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    await wrapper.get('[data-test="alerts-select-all"] input').setValue(true)
    await wrapper.get('[data-test="alerts-bulk-resolve"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('3 alertas seleccionadas')
    expect(api.resolveAlerts).not.toHaveBeenCalled() // antes de confirmar no se manda nada

    await wrapper.get('textarea').setValue('  Revisadas  ')
    await wrapper.get('[data-test="resolve-confirm"]').trigger('click')
    await flushPromises()

    expect(api.resolveAlerts).toHaveBeenCalledTimes(1)
    expect(api.resolveAlerts).toHaveBeenCalledWith(['a1', 'a2', 'a3'], 'Revisadas')
    expect(toast.success).toHaveBeenCalledWith('3 alertas resueltas', { description: undefined })
    expect(api.alerts).toHaveBeenCalledTimes(2)
  })

  it('si el backend falla avisa y deja la selección para reintentar', async () => {
    api.acknowledgeAlerts.mockRejectedValue(new Error('sin red'))
    const wrapper = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    await pick(wrapper, 0)?.setValue(true)
    await wrapper.get('[data-test="alerts-bulk-ack"]').trigger('click')
    await flushPromises()

    expect(toast.error).toHaveBeenCalled()
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('1 seleccionada')
  })

  it('en pantallas angostas la selección también funciona desde las tarjetas', async () => {
    viewport = 390
    const wrapper = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    await pick(wrapper, 1)?.setValue(true)
    expect(wrapper.get('[data-test="alerts-selected-count"]').text()).toBe('1 seleccionada')
  })
})
