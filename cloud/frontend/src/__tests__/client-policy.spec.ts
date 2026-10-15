import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AccessPolicy, AiPolicy, Client } from '@/lib/types'

const api = vi.hoisted(() => ({
  clientDatabases: vi.fn(),
  clientPeople: vi.fn(),
  setClientPolicy: vi.fn(),
  setClientAiPolicy: vi.fn(),
  setClientAccessPolicy: vi.fn(),
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

import AccessPolicyCard from '@/components/AccessPolicyCard.vue'
import AiPolicyCard from '@/components/AiPolicyCard.vue'
import ClientPolicyCard from '@/components/ClientPolicyCard.vue'

const DB_1 = '7a1f3c52-9d4e-4b6a-8c0d-1e2f3a4b5c6d'
const DB_2 = '11111111-2222-4333-8444-555555555555'
const PERSON = 'a'.repeat(32)
// Persona ya configurada que no figura en el padrón (nunca reportó o se perdió el dato).
const GHOST = 'f'.repeat(32)

const AI_POLICY: AiPolicy = {
  allowed_providers: null,
  user_monthly_usd: null,
  provider_monthly_usd: {},
  user_overrides: {},
}
const ACCESS_POLICY: AccessPolicy = { default_databases: null, user_databases: {}, groups: [] }

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
  ai_policy: AI_POLICY,
  access_policy: ACCESS_POLICY,
}

/** El `data-test` va en el contenedor del campo: el control es el de adentro. */
function control(wrapper: VueWrapper, name: string) {
  const root = wrapper.get(`[data-test="${name}"]`)
  return root.element.matches('input, select, textarea, button')
    ? root
    : root.get('input, select, textarea, button[role="switch"]')
}

async function saveWithBar(wrapper: VueWrapper) {
  await wrapper.get('[data-test="unsaved-save"]').trigger('click')
  await flushPromises()
  await wrapper.get('[data-test="confirm-accept"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
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
  api.clientPeople.mockResolvedValue([
    { user_ref: PERSON, label: 'JPEREZ', sessions: 3, last_session_at: '2026-10-01T00:00:00Z' },
  ])
})

describe('política de las instalaciones del cliente', () => {
  function mountCard(client: Client = CLIENT) {
    return mount(ClientPolicyCard, { props: { clientId: 'c1', client } })
  }

  it('bloquear la configuración pide confirmación, llama al API y confirma', async () => {
    const wrapper = mountCard()

    await wrapper.get('[data-test="toggle-lock"]').trigger('click')
    expect(api.setClientPolicy).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Dejar las instalaciones solo con el chat')

    await wrapper.get('[data-test="confirm-accept"]').trigger('click')
    await flushPromises()

    expect(api.setClientPolicy).toHaveBeenCalledWith('c1', { config_locked: true })
    expect(toast.success).toHaveBeenCalled()
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('identificar a las personas advierte que es solo para la organización interna', async () => {
    const wrapper = mountCard()

    await wrapper.get('[data-test="toggle-identity"]').trigger('click')

    expect(wrapper.text()).toContain('organización interna')
    await wrapper.get('[data-test="confirm-accept"]').trigger('click')
    await flushPromises()
    expect(api.setClientPolicy).toHaveBeenCalledWith('c1', { identity_mode: 'named' })
  })

  it('permitir el CLI de Claude pide confirmación y manda solo ese campo', async () => {
    const wrapper = mountCard()

    await wrapper.get('[data-test="toggle-cli"]').trigger('click')
    expect(wrapper.text()).toContain('con su propia cuenta')
    await wrapper.get('[data-test="confirm-accept"]').trigger('click')
    await flushPromises()

    expect(api.setClientPolicy).toHaveBeenCalledWith('c1', { allow_local_cli: true })
  })

  it('un cliente ya bloqueado ofrece permitir la configuración', () => {
    const wrapper = mountCard({ ...CLIENT, config_locked: true })

    expect(wrapper.get('[data-test="toggle-lock"]').text()).toBe('Permitir configuración')
    expect(wrapper.text()).toContain('Bloqueada')
  })

  it('si el servidor rechaza, avisa con un toast de error', async () => {
    api.setClientPolicy.mockRejectedValue(new Error('Sin permiso.'))
    const wrapper = mountCard()

    await wrapper.get('[data-test="toggle-lock"]').trigger('click')
    await wrapper.get('[data-test="confirm-accept"]').trigger('click')
    await flushPromises()

    expect(toast.error).toHaveBeenCalledWith('No se pudo cambiar la política', {
      description: 'Sin permiso.',
    })
    expect(wrapper.emitted('saved')).toBeUndefined()
  })
})

describe('IA: proveedores y topes del cliente', () => {
  async function mountCard(policy: AiPolicy = AI_POLICY) {
    const wrapper = mount(AiPolicyCard, { props: { clientId: 'c1', policy } })
    await flushPromises()
    return wrapper
  }

  it('sin cambios no muestra la barra de guardar', async () => {
    const wrapper = await mountCard()

    expect(wrapper.find('[data-test="unsaved-save"]').exists()).toBe(false)
  })

  it('guarda el tope por persona y manda todos los proveedores como null', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'ai-user-cap').setValue('5')
    await saveWithBar(wrapper)

    expect(api.setClientAiPolicy).toHaveBeenCalledWith('c1', {
      allowed_providers: null,
      user_monthly_usd: '5',
      provider_monthly_usd: {},
      user_overrides: {},
    })
    expect(toast.success).toHaveBeenCalled()
  })

  it('desmarcar un proveedor y fijar su tope viaja en el cuerpo', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'ai-provider-openai').setValue(false)
    await control(wrapper, 'ai-provider-cap-gemini').setValue('50')
    await saveWithBar(wrapper)

    expect(api.setClientAiPolicy).toHaveBeenCalledWith('c1', {
      allowed_providers: ['claude', 'gemini'],
      user_monthly_usd: null,
      provider_monthly_usd: { gemini: '50' },
      user_overrides: {},
    })
  })

  it('agrega una excepción por persona usando su código de usuario', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'ai-override-person').setValue(PERSON)
    await control(wrapper, 'ai-override-amount').setValue('20')
    await wrapper.get('[data-test="ai-override-add"]').trigger('click')

    expect(wrapper.get('[data-test="ai-override"]').text()).toContain('JPEREZ')
    await saveWithBar(wrapper)
    expect(api.setClientAiPolicy).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({ user_overrides: { [PERSON]: '20' } }),
    )
  })

  it('una excepción sin persona o con monto inválido marca los campos', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'ai-override-amount').setValue('veinte')
    await wrapper.get('[data-test="ai-override-add"]').trigger('click')

    expect(wrapper.get('[data-test="ai-override-person"]').text()).toContain('Elegí una persona')
    expect(wrapper.get('[data-test="ai-override-amount"]').text()).toContain('USD')
    expect(wrapper.find('[data-test="ai-override"]').exists()).toBe(false)
  })

  it('rechaza montos inválidos en el campo, sin llamar al API', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'ai-user-cap').setValue('-5')
    await wrapper.get('[data-test="unsaved-save"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="ai-user-cap"]').text()).toContain('USD')
    expect(wrapper.find('[data-test="confirm-accept"]').exists()).toBe(false)
    expect(api.setClientAiPolicy).not.toHaveBeenCalled()
  })

  it('no deja guardar sin ningún proveedor habilitado', async () => {
    const wrapper = await mountCard()

    for (const key of ['claude', 'gemini', 'openai']) {
      await control(wrapper, `ai-provider-${key}`).setValue(false)
    }
    await wrapper.get('[data-test="unsaved-save"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="ai-error"]').text()).toContain('al menos un proveedor')
    expect(api.setClientAiPolicy).not.toHaveBeenCalled()
  })

  it('avisa que Gemini y OpenAI necesitan precios cuando hay un tope', async () => {
    const wrapper = await mountCard()
    expect(wrapper.find('[data-test="ai-price-warning"]').exists()).toBe(false)

    await control(wrapper, 'ai-user-cap').setValue('5')

    expect(wrapper.get('[data-test="ai-price-warning"]').text()).toContain('precios')
  })

  it('una excepción guardada de alguien fuera del padrón se muestra y se puede quitar', async () => {
    const wrapper = await mountCard({ ...AI_POLICY, user_overrides: { [GHOST]: '5' } })

    const row = wrapper.get('[data-test="ai-override"]')
    expect(row.text()).toContain('Persona sin actividad reciente (ffffffff…)')

    await row.get('button').trigger('click')
    expect(wrapper.find('[data-test="ai-override"]').exists()).toBe(false)
  })

  it('las excepciones se ofrecen sobre todo el padrón, no solo sobre quien usó hace poco', async () => {
    const wrapper = await mountCard()

    expect(api.clientPeople).toHaveBeenCalledWith('c1')
    expect(wrapper.get('[data-test="ai-override-person"]').text()).toContain('JPEREZ')
  })

  it('descartar vuelve a lo guardado', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'ai-user-cap').setValue('5')
    await wrapper.get('[data-test="unsaved-discard"]').trigger('click')

    expect((control(wrapper, 'ai-user-cap').element as HTMLInputElement).value).toBe('')
    expect(wrapper.find('[data-test="unsaved-save"]').exists()).toBe(false)
  })
})

describe('bases por persona', () => {
  async function mountCard(policy: AccessPolicy = ACCESS_POLICY) {
    const wrapper = mount(AccessPolicyCard, { props: { clientId: 'c1', policy } })
    await flushPromises()
    return wrapper
  }

  it('limitar por defecto manda solo las bases marcadas', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'access-limit-default').trigger('click')
    await control(wrapper, `access-default-${DB_1}`).setValue(true)
    await saveWithBar(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: [DB_1],
      user_databases: {},
      groups: [],
    })
    expect(toast.success).toHaveBeenCalled()
  })

  it('volver a "sin límite" manda null', async () => {
    const wrapper = await mountCard({ ...ACCESS_POLICY, default_databases: [DB_1] })

    await control(wrapper, 'access-limit-default').trigger('click')
    await saveWithBar(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: null,
      user_databases: {},
      groups: [],
    })
  })

  it('una regla por persona con bases marcadas', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'access-rule-person').setValue(PERSON)
    await wrapper.get('[data-test="access-rule-add"]').trigger('click')
    expect(wrapper.get('[data-test="access-rule"]').text()).toContain('JPEREZ')
    await control(wrapper, `access-rule-${PERSON}-${DB_2}`).setValue(true)
    await saveWithBar(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: null,
      user_databases: { [PERSON]: [DB_2] },
      groups: [],
    })
  })

  it('avisa cuando una regla queda sin ninguna base', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'access-rule-person').setValue(PERSON)
    await wrapper.get('[data-test="access-rule-add"]').trigger('click')

    expect(wrapper.get('[data-test="access-rule-empty"]').text()).toContain('no podrán consultar')
  })

  it('arma un grupo con personas y bases', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'access-group-name').setValue('Soporte norte')
    await wrapper.get('[data-test="access-group-add"]').trigger('submit')
    expect(wrapper.get('[data-test="access-group"]').text()).toContain('Soporte norte')
    await control(wrapper, `access-group-Soporte norte-person-${PERSON}`).setValue(true)
    await control(wrapper, `access-group-Soporte norte-db-${DB_1}`).setValue(true)
    await saveWithBar(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith('c1', {
      default_databases: null,
      user_databases: {},
      groups: [
        {
          id: null,
          name: 'Soporte norte',
          members: [PERSON],
          databases: [DB_1],
          user_monthly_usd: null,
        },
      ],
    })
  })

  it('un miembro guardado que no está en el padrón se ve con su casilla y se puede quitar', async () => {
    const wrapper = await mountCard({
      ...ACCESS_POLICY,
      groups: [
        { id: 'g1', name: 'Norte', members: [GHOST], databases: [], user_monthly_usd: null },
      ],
    })

    const member = wrapper.get(`[data-test="access-group-Norte-person-${GHOST}"]`)
    expect(member.text()).toContain('Persona sin actividad reciente (ffffffff…)')
    expect(
      (control(wrapper, `access-group-Norte-person-${GHOST}`).element as HTMLInputElement).checked,
    ).toBe(true)

    await control(wrapper, `access-group-Norte-person-${GHOST}`).setValue(false)
    await saveWithBar(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({
        groups: [expect.objectContaining({ name: 'Norte', members: [] })],
      }),
    )
  })

  it('no permite dos grupos con el mismo nombre y lo dice en el campo', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'access-group-name').setValue('Norte')
    await wrapper.get('[data-test="access-group-add"]').trigger('submit')
    await control(wrapper, 'access-group-name').setValue('norte')
    await wrapper.get('[data-test="access-group-add"]').trigger('submit')

    expect(wrapper.findAll('[data-test="access-group"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="access-group-name"]').text()).toContain('ese nombre')
  })

  it('un grupo puede fijar el tope mensual de IA de sus miembros', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'access-group-name').setValue('Soporte')
    await wrapper.get('[data-test="access-group-add"]').trigger('submit')
    await control(wrapper, 'access-group-Soporte-cap').setValue(' 7.5 ')
    await saveWithBar(wrapper)

    expect(api.setClientAccessPolicy).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({
        groups: [expect.objectContaining({ name: 'Soporte', user_monthly_usd: '7.5' })],
      }),
    )
  })

  it('un tope de grupo inválido se marca y no se guarda', async () => {
    const wrapper = await mountCard()

    await control(wrapper, 'access-group-name').setValue('Soporte')
    await wrapper.get('[data-test="access-group-add"]').trigger('submit')
    await control(wrapper, 'access-group-Soporte-cap').setValue('mucho')
    await wrapper.get('[data-test="unsaved-save"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="access-group-Soporte-cap"]').text()).toContain('USD')
    expect(api.setClientAccessPolicy).not.toHaveBeenCalled()
  })
})
