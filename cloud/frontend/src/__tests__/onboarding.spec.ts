import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClientOnboarding, Permission } from '@/lib/types'

const api = vi.hoisted(() => ({ clientOnboarding: vi.fn() }))
vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))

import OnboardingChecklist from '@/components/OnboardingChecklist.vue'
import { buildOnboardingSteps } from '@/lib/onboarding'
import { useAuthStore } from '@/stores/authStore'

const NOTHING: ClientOnboarding = {
  plan_loaded: false,
  policy_defined: false,
  ai_defined: false,
  token_created: false,
  instance_connected: false,
  report_received: false,
}

const ALL_PERMISSIONS: Permission[] = [
  'clients.read',
  'clients.billing',
  'clients.policy',
  'tokens.manage',
]

async function mountChecklist(
  state: ClientOnboarding,
  permissions: Permission[] = ALL_PERMISSIONS,
) {
  const auth = useAuthStore()
  auth.user = { id: 'u1', email: 'a@b.co', full_name: 'Ana', role: 'admin', permissions }
  auth.accessToken = 'tok'
  api.clientOnboarding.mockResolvedValue(state)
  const wrapper = mount(OnboardingChecklist, {
    props: { clientId: 'c1' },
    global: { stubs: { RouterLink: RouterLinkStub } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('pasos de la puesta en marcha', () => {
  it.each([
    ['plan_loaded', 'Plan cargado'],
    ['policy_defined', 'Política definida'],
    ['ai_defined', 'Límites de IA definidos'],
    ['token_created', 'Token de vinculación generado'],
    ['instance_connected', 'Primera instalación en línea'],
    ['report_received', 'Primer reporte recibido'],
  ] as const)('el paso "%s" se marca solo con su dato', (key, label) => {
    const pending = buildOnboardingSteps(NOTHING, () => true).find((s) => s.key === key)
    const done = buildOnboardingSteps({ ...NOTHING, [key]: true }, () => true).find(
      (s) => s.key === key,
    )

    expect(pending).toMatchObject({ label, done: false })
    expect(done).toMatchObject({ label, done: true })
  })

  it('sin el permiso del paso lo deja pendiente del rol que sí puede', () => {
    const steps = buildOnboardingSteps(NOTHING, () => false)
    const roles = Object.fromEntries(steps.map((s) => [s.key, s.pendingRole]))

    expect(roles).toEqual({
      plan_loaded: 'Comercial',
      policy_defined: 'Administrador',
      ai_defined: 'Administrador',
      token_created: 'Soporte',
      instance_connected: null,
      report_received: null,
    })
  })

  it('un paso hecho nunca queda pendiente de un rol', () => {
    const steps = buildOnboardingSteps({ ...NOTHING, plan_loaded: true }, () => false)

    expect(steps[0]?.pendingRole).toBeNull()
  })
})

describe('tarjeta "Puesta en marcha"', () => {
  it('lista los seis pasos con su avance y enlaza cada uno a su pestaña', async () => {
    const wrapper = await mountChecklist({ ...NOTHING, plan_loaded: true })

    expect(wrapper.text()).toContain('1 de 6 pasos completos')
    expect(wrapper.get('[data-test="onboarding-plan_loaded"]').attributes('data-state')).toBe(
      'done',
    )
    expect(wrapper.get('[data-test="onboarding-policy_defined"]').attributes('data-state')).toBe(
      'pending',
    )
    const links = wrapper.findAllComponents(RouterLinkStub).map((l) => l.props('to'))
    expect(links).toEqual([
      '/clientes/c1/politica',
      '/clientes/c1/ia',
      '/clientes/c1/vinculacion',
      '/clientes/c1/instancias',
      '/clientes/c1/sucursales',
    ])
  })

  it('destaca como siguiente el primer paso pendiente que esta persona puede hacer', async () => {
    const wrapper = await mountChecklist(NOTHING, ['clients.read', 'tokens.manage'])

    // Plan, política e IA son de otros roles: lo siguiente es generar el token.
    expect(wrapper.get('[data-test="onboarding-token_created"]').text()).toContain('Siguiente')
    expect(wrapper.get('[data-test="onboarding-plan_loaded"]').text()).not.toContain('Siguiente')
  })

  it('sin permiso muestra "Pendiente de <rol>" en vez de un enlace', async () => {
    const wrapper = await mountChecklist(NOTHING, ['clients.read'])
    const plan = wrapper.get('[data-test="onboarding-plan_loaded"]')

    expect(plan.get('[data-test="onboarding-role"]').text()).toBe('Pendiente de Comercial')
    expect(plan.findComponent(RouterLinkStub).exists()).toBe(false)
    expect(wrapper.get('[data-test="onboarding-token_created"]').text()).toContain(
      'Pendiente de Soporte',
    )
    // Instalación y reporte no dependen de un permiso: siguen enlazados a su pestaña.
    expect(
      wrapper
        .get('[data-test="onboarding-instance_connected"]')
        .findComponent(RouterLinkStub)
        .exists(),
    ).toBe(true)
  })

  it('con todo hecho se reduce a una línea y no deja la tarjeta', async () => {
    const wrapper = await mountChecklist({
      plan_loaded: true,
      policy_defined: true,
      ai_defined: true,
      token_created: true,
      instance_connected: true,
      report_received: true,
    })

    expect(wrapper.get('[data-test="onboarding-complete"]').text()).toBe(
      'Puesta en marcha completa',
    )
    expect(wrapper.find('[data-test="onboarding"]').exists()).toBe(false)
  })

  it('si no carga, no muestra nada: no estorba al resto del resumen', async () => {
    api.clientOnboarding.mockRejectedValue(new Error('caído'))
    const wrapper = mount(OnboardingChecklist, {
      props: { clientId: 'c1' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await flushPromises()

    expect(wrapper.find('[data-test="onboarding"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="onboarding-complete"]').exists()).toBe(false)
  })
})
