import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ApiError } from '@/lib/http'
import type { Alert, AlertRule, Client, StaffMember } from '@/lib/types'

const api = vi.hoisted(() => ({
  clients: vi.fn(),
  createClient: vi.fn(),
  alerts: vi.fn(),
  alertRules: vi.fn(),
  acknowledgeAlert: vi.fn(),
  resolveAlert: vi.fn(),
  updateRule: vi.fn(),
  staff: vi.fn(),
  createStaff: vi.fn(),
  updateStaff: vi.fn(),
  staffAction: vi.fn(),
  audit: vi.fn(),
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

import { resetRuleTitlesForTests } from '@/lib/ruleTitles'
import { useAuthStore } from '@/stores/authStore'
import AlertRulesView from '@/views/AlertRulesView.vue'
import AlertsView from '@/views/AlertsView.vue'
import AuditView from '@/views/AuditView.vue'
import ClientsView from '@/views/ClientsView.vue'
import StaffView from '@/views/StaffView.vue'

const ALERT: Alert = {
  id: 'a1',
  rule_code: 'subscription_due',
  severity: 'critical',
  status: 'open',
  client_id: 'c1',
  instance_id: null,
  details: { days_left: 2 },
  opened_at: '2026-10-01T00:00:00Z',
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolved_by: null,
  resolution_note: null,
}

const RULE: AlertRule = {
  code: 'instance_offline',
  title: 'Instancia sin conexión',
  description: 'Una instancia dejó de contactar a Cloud.',
  enabled: true,
  severity: 'warning',
  threshold: 2,
  threshold_unit: 'horas',
  default_threshold: 2,
  auto_resolve: true,
} as AlertRule

const MEMBER: StaffMember = {
  id: 's2',
  email: 'soporte@seo.example',
  full_name: 'Sofía Soporte',
  role: 'soporte',
  is_active: true,
  mfa_enabled: true,
  last_login_at: null,
} as StaffMember

async function mountView(component: object, permissions: string[] = []) {
  const auth = useAuthStore()
  auth.user = {
    id: 's1',
    email: 'admin@seo.example',
    full_name: 'Ana',
    role: 'admin',
    permissions: permissions as never,
  }
  auth.accessToken = 'tok'
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/clientes/:id', component: { template: '<div>detalle</div>' } },
      { path: '/:p(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  const wrapper = mount(component, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

/** El `data-test` va en el contenedor del campo: el control es el de adentro. */
function control(wrapper: VueWrapper, name: string) {
  return wrapper.get(`[data-test="${name}"] input, [data-test="${name}"] select`)
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  resetRuleTitlesForTests()
  document.body.innerHTML = ''
  api.alertRules.mockResolvedValue([
    { ...RULE, code: 'subscription_due', title: 'Suscripción por vencer' },
  ])
})

describe('clientes', () => {
  beforeEach(() => {
    api.clients.mockResolvedValue({ items: [], total: 0 })
  })

  it('sin clientes invita a crear el primero', async () => {
    const { wrapper } = await mountView(ClientsView, ['clients.read', 'clients.write'])

    expect(wrapper.text()).toContain('Todavía no hay clientes')
  })

  it('crear un cliente pasa el código a mayúsculas y abre su detalle', async () => {
    api.createClient.mockResolvedValue({ id: 'c9', code: 'FARMY' })
    const { wrapper, router } = await mountView(ClientsView, ['clients.read', 'clients.write'])

    await wrapper.get('[data-test="client-new"]').trigger('click')
    await control(wrapper, 'client-code').setValue('farmy')
    await control(wrapper, 'client-name').setValue('Farmacias Y')
    await wrapper.get('#client-form').trigger('submit')
    await flushPromises()

    expect(api.createClient).toHaveBeenCalledWith({ code: 'FARMY', name: 'Farmacias Y', nit: null })
    expect(router.currentRoute.value.path).toBe('/clientes/c9')
  })

  it('un código inválido se marca en el campo y no se envía', async () => {
    const { wrapper } = await mountView(ClientsView, ['clients.read', 'clients.write'])

    await wrapper.get('[data-test="client-new"]').trigger('click')
    await control(wrapper, 'client-code').setValue('x')
    await control(wrapper, 'client-name').setValue('Algo')
    await wrapper.get('#client-form').trigger('submit')
    await flushPromises()

    expect(api.createClient).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="client-code"]').text()).toContain('Entre 2 y 32')
  })

  it('un código repetido vuelve al campo con el mensaje del servidor', async () => {
    api.createClient.mockRejectedValue(
      new ApiError(400, 'client_code_already_exists', 'Ya existe un cliente con el código DEMO.'),
    )
    const { wrapper } = await mountView(ClientsView, ['clients.read', 'clients.write'])

    await wrapper.get('[data-test="client-new"]').trigger('click')
    await control(wrapper, 'client-code').setValue('DEMO')
    await control(wrapper, 'client-name').setValue('Otro')
    await wrapper.get('#client-form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-test="client-code"]').text()).toContain('Ya existe un cliente')
  })

  it('pide de a 50 y "Ver más" trae el siguiente tramo sin mentir en el conteo', async () => {
    const page = (from: number, count: number) =>
      Array.from(
        { length: count },
        (_, n) =>
          ({
            id: `c${from + n}`,
            code: `C${from + n}`,
            name: `Cliente ${from + n}`,
            status: 'active',
            instances_online: 0,
            instances_total: 0,
            last_seen_at: null,
            oldest_version: null,
          }) as unknown as Client,
      )
    api.clients
      .mockResolvedValueOnce({ items: page(0, 50), total: 120 })
      .mockResolvedValueOnce({ items: page(50, 50), total: 120 })
      .mockResolvedValueOnce({ items: page(100, 20), total: 120 })
    const { wrapper } = await mountView(ClientsView, ['clients.read'])

    expect(api.clients).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 0 }))
    expect(wrapper.get('[data-test="clients-total"]').text()).toBe('Mostrando 50 de 120 clientes')

    await wrapper.get('[data-test="clients-more"]').trigger('click')
    await flushPromises()
    expect(api.clients).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 50 }))
    expect(wrapper.get('[data-test="clients-total"]').text()).toBe('Mostrando 100 de 120 clientes')

    await wrapper.get('[data-test="clients-more"]').trigger('click')
    await flushPromises()
    expect(api.clients).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 100 }))
    expect(wrapper.get('[data-test="clients-total"]').text()).toBe('120 clientes')
    expect(wrapper.find('[data-test="clients-more"]').exists()).toBe(false)
  })

  it('sin permiso de escritura no ofrece crear', async () => {
    const { wrapper } = await mountView(ClientsView, ['clients.read'])

    expect(wrapper.find('[data-test="client-new"]').exists()).toBe(false)
  })
})

describe('alertas', () => {
  beforeEach(() => {
    api.alerts.mockResolvedValue([ALERT])
    api.acknowledgeAlert.mockResolvedValue({ ...ALERT, status: 'acknowledged' })
    api.resolveAlert.mockResolvedValue({ ...ALERT, status: 'resolved' })
  })

  it('arranca mostrando las abiertas y con el título de la regla', async () => {
    const { wrapper } = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    expect(api.alerts).toHaveBeenCalledWith({ status: 'open', severity: undefined })
    expect(wrapper.text()).toContain('Suscripción por vencer')
  })

  it('muestra el detalle legible y el nombre del cliente', async () => {
    api.alerts.mockResolvedValue([
      {
        ...ALERT,
        client_name: 'Farmacias X',
        details: { valid_until: '2026-10-03', days_left: 2 },
      },
    ])
    const { wrapper } = await mountView(AlertsView, ['alerts.read'])

    expect(wrapper.text()).toContain('Vence el 03/10/2026 · quedan 2 días')
    expect(wrapper.text()).not.toContain('days_left')
    expect(wrapper.get('[data-test="alert-client"]').text()).toBe('Farmacias X')
  })

  it('reconocer avisa y recarga', async () => {
    const { wrapper } = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Reconocer')
      ?.trigger('click')
    await flushPromises()

    expect(api.acknowledgeAlert).toHaveBeenCalledWith('a1')
    expect(toast.success).toHaveBeenCalledWith('Alerta reconocida')
    expect(api.alerts).toHaveBeenCalledTimes(2)
  })

  it('resolver pide una nota en un diálogo y la envía', async () => {
    const { wrapper } = await mountView(AlertsView, ['alerts.read', 'alerts.manage'])

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Resolver')
      ?.trigger('click')
    await flushPromises()
    await wrapper.get('textarea').setValue('  Renovó por transferencia  ')
    await wrapper.get('[data-test="resolve-confirm"]').trigger('click')
    await flushPromises()

    expect(api.resolveAlert).toHaveBeenCalledWith('a1', 'Renovó por transferencia')
    expect(toast.success).toHaveBeenCalledWith('Alerta resuelta')
  })

  it('sin permiso de gestión no ofrece acciones', async () => {
    const { wrapper } = await mountView(AlertsView, ['alerts.read'])

    expect(wrapper.findAll('button').some((b) => b.text() === 'Reconocer')).toBe(false)
  })
})

describe('reglas de alerta', () => {
  beforeEach(() => {
    api.alertRules.mockResolvedValue([RULE])
    api.updateRule.mockResolvedValue(RULE)
  })

  it('apagar una regla la guarda y avisa', async () => {
    const { wrapper } = await mountView(AlertRulesView, ['alerts.configure'])

    await wrapper
      .get('[data-test="rule-instance_offline-enabled"] [role="switch"]')
      .trigger('click')
    await flushPromises()

    expect(api.updateRule).toHaveBeenCalledWith('instance_offline', { enabled: false })
    expect(toast.success).toHaveBeenCalledWith('Regla apagada')
  })

  it('un umbral de cero se marca y no se guarda', async () => {
    const { wrapper } = await mountView(AlertRulesView, ['alerts.configure'])

    await control(wrapper, 'rule-instance_offline-threshold').setValue('0')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.updateRule).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('mayor que cero')
  })

  it('un umbral válido se guarda', async () => {
    const { wrapper } = await mountView(AlertRulesView, ['alerts.configure'])

    await control(wrapper, 'rule-instance_offline-threshold').setValue('6')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.updateRule).toHaveBeenCalledWith('instance_offline', { threshold: 6 })
  })
})

describe('equipo', () => {
  beforeEach(() => {
    api.staff.mockResolvedValue([MEMBER])
    api.createStaff.mockResolvedValue({ member: MEMBER, temporary_password: 'Temp-Clave-123' })
    api.updateStaff.mockResolvedValue(MEMBER)
  })

  it('crear un usuario valida, envía y muestra la contraseña temporal una vez', async () => {
    const { wrapper } = await mountView(StaffView, ['staff.manage'])

    await wrapper.get('[data-test="staff-new"]').trigger('click')
    await control(wrapper, 'staff-email').setValue('nuevo@seo.example')
    await control(wrapper, 'staff-name').setValue('Nuevo Integrante')
    await wrapper.get('#staff-form').trigger('submit')
    await flushPromises()

    expect(api.createStaff).toHaveBeenCalledWith({
      email: 'nuevo@seo.example',
      full_name: 'Nuevo Integrante',
      role: 'soporte',
    })
    expect(wrapper.text()).toContain('Temp-Clave-123')
  })

  it('un correo inválido no se envía', async () => {
    const { wrapper } = await mountView(StaffView, ['staff.manage'])

    await wrapper.get('[data-test="staff-new"]').trigger('click')
    await control(wrapper, 'staff-email').setValue('no-es-correo')
    await control(wrapper, 'staff-name').setValue('Alguien')
    await wrapper.get('#staff-form').trigger('submit')
    await flushPromises()

    expect(api.createStaff).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="staff-email"]').text()).toContain('correo válido')
  })

  it('cambiar el rol pide confirmación antes de guardarlo', async () => {
    const { wrapper } = await mountView(StaffView, ['staff.manage'])

    await wrapper.get('select[aria-label="Rol de Sofía Soporte"]').setValue('admin')
    expect(api.updateStaff).not.toHaveBeenCalled()
    await wrapper.get('[data-test="confirm-accept"]').trigger('click')
    await flushPromises()

    expect(api.updateStaff).toHaveBeenCalledWith('s2', { role: 'admin' })
  })
})

describe('auditoría', () => {
  it('filtra por quién y por acción', async () => {
    api.audit.mockResolvedValue({ items: [], next_cursor: null })
    const { wrapper } = await mountView(AuditView, ['audit.read'])

    const [actor, action] = wrapper.findAll('form input')
    await actor?.setValue('ana@seo.example')
    await action?.setValue('client.update')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(api.audit).toHaveBeenLastCalledWith({
      actor: 'ana@seo.example',
      action: 'client.update',
      cursor: undefined,
    })
    expect(wrapper.text()).toContain('No hay registros con esos filtros')
  })
})
