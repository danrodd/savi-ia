import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { EnrollmentToken, Instance } from '@/lib/types'

const api = vi.hoisted(() => ({
  createToken: vi.fn(),
  revokeToken: vi.fn(),
  instances: vi.fn(),
}))

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

import ClientTokensPanel from '@/components/ClientTokensPanel.vue'

const PENDING: EnrollmentToken = {
  id: 't1',
  state: 'pending',
  created_at: '2026-10-01T10:00:00Z',
  expires_at: '2026-10-04T10:00:00Z',
  created_by: 'admin@seo.example',
  used_at: null,
  used_by_instance_id: null,
  revoked_at: null,
}

function mountPanel(tokens: EnrollmentToken[] = [], loading = false, canManage = true) {
  return mount(ClientTokensPanel, {
    props: { clientId: 'c1', tokens, loading, canManage },
    global: { stubs: { RouterLink: RouterLinkStub } },
  })
}

const NEW_INSTANCE = { id: 'i2', name: 'SRV-NUEVA' } as Instance

beforeEach(() => {
  vi.clearAllMocks()
  api.createToken.mockResolvedValue({ token: 'svk_enr_secreto' })
  api.revokeToken.mockResolvedValue(undefined)
  api.instances.mockResolvedValue([])
})

describe('tokens de vinculación', () => {
  it('sin tokens avisa que todavía no se generó ninguno', () => {
    const wrapper = mountPanel([])

    expect(wrapper.text()).toContain('Todavía no se generó ningún token')
  })

  it('no muestra el aviso de vacío mientras carga', () => {
    const wrapper = mountPanel([], true)

    expect(wrapper.text()).not.toContain('Todavía no se generó ningún token')
  })

  it('generar un token lo pide con la vigencia elegida y lo muestra una sola vez', async () => {
    const wrapper = mountPanel()

    await wrapper.get('[data-test="token-duration"] select').setValue('24')
    await wrapper.get('[data-test="token-create"]').trigger('click')
    await flushPromises()

    expect(api.createToken).toHaveBeenCalledWith('c1', 24)
    expect(wrapper.text()).toContain('svk_enr_secreto')
  })

  it('al cerrar el diálogo avisa que hay que recargar y descarta el secreto', async () => {
    const wrapper = mountPanel()
    await wrapper.get('[data-test="token-create"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-test="secret-close"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('svk_enr_secreto')
  })

  it('revocar pide confirmación, llama al API y avisa el cambio', async () => {
    const wrapper = mountPanel([PENDING])

    await wrapper.get('[data-test="token-revoke"]').trigger('click')
    expect(api.revokeToken).not.toHaveBeenCalled()

    await wrapper.get('[data-test="confirm-accept"]').trigger('click')
    await flushPromises()

    expect(api.revokeToken).toHaveBeenCalledWith('t1')
    expect(toast.success).toHaveBeenCalledWith('Token revocado')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('si falla la generación avisa con un toast de error', async () => {
    api.createToken.mockRejectedValue(new Error('El cliente está suspendido.'))
    const wrapper = mountPanel()

    await wrapper.get('[data-test="token-create"]').trigger('click')
    await flushPromises()

    expect(toast.error).toHaveBeenCalledWith('No se pudo generar el token', {
      description: 'El cliente está suspendido.',
    })
  })

  it('un token usado no ofrece revocar', () => {
    const wrapper = mountPanel([{ ...PENDING, state: 'used' }])

    expect(wrapper.find('[data-test="token-revoke"]').exists()).toBe(false)
  })
})

describe('vinculación guiada', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  async function generateAndClose(wrapper: ReturnType<typeof mountPanel>) {
    await wrapper.get('[data-test="token-create"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="secret-close"]').trigger('click')
    await flushPromises()
  }

  it('muestra los tres pasos y la dirección de Cloud junto al token', async () => {
    const wrapper = mountPanel()
    expect(wrapper.findAll('.ui-stepper__step')).toHaveLength(3)

    await wrapper.get('[data-test="token-create"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(window.location.origin)
    expect(wrapper.text()).toContain('Pégalo')
    expect(wrapper.find('[data-test="link-step-install"]').exists()).toBe(true)
  })

  it('al cerrar el token espera la conexión y avisa cuando aparece una instalación nueva', async () => {
    api.instances.mockResolvedValue([{ id: 'i1', name: 'Vieja' }])
    const wrapper = mountPanel()
    await generateAndClose(wrapper)

    expect(wrapper.find('[data-test="link-step-waiting"]').exists()).toBe(true)
    // Una instalación que ya existía no cuenta.
    await vi.advanceTimersByTimeAsync(5_000)
    expect(wrapper.find('[data-test="link-step-linked"]').exists()).toBe(false)

    api.instances.mockResolvedValue([{ id: 'i1', name: 'Vieja' }, NEW_INSTANCE])
    await vi.advanceTimersByTimeAsync(5_000)
    await flushPromises()

    expect(wrapper.get('[data-test="link-step-linked"]').text()).toContain('Instalación vinculada')
    const link = wrapper.getComponent(RouterLinkStub)
    expect(link.props('to')).toBe('/instancias/i2')
    expect(link.text()).toBe('SRV-NUEVA')
    // Refresca la lista de tokens (el usado deja de estar vigente).
    expect(wrapper.emitted('changed')).toHaveLength(2)
  })

  it('consulta cada 5 segundos y deja de consultar al encontrarla', async () => {
    const wrapper = mountPanel()
    await generateAndClose(wrapper)
    const baseline = api.instances.mock.calls.length

    await vi.advanceTimersByTimeAsync(15_000)
    expect(api.instances.mock.calls.length - baseline).toBe(3)

    api.instances.mockResolvedValue([NEW_INSTANCE])
    await vi.advanceTimersByTimeAsync(5_000)
    const afterFound = api.instances.mock.calls.length
    await vi.advanceTimersByTimeAsync(30_000)

    expect(api.instances).toHaveBeenCalledWith({ client_id: 'c1' })
    expect(api.instances.mock.calls.length).toBe(afterFound)
  })

  it('deja de consultar al desmontar', async () => {
    const wrapper = mountPanel()
    await generateAndClose(wrapper)
    await vi.advanceTimersByTimeAsync(5_000)
    wrapper.unmount()
    const calls = api.instances.mock.calls.length

    await vi.advanceTimersByTimeAsync(60_000)

    expect(api.instances.mock.calls.length).toBe(calls)
  })

  it('no consulta con la pestaña oculta', async () => {
    const wrapper = mountPanel()
    await generateAndClose(wrapper)
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
    const calls = api.instances.mock.calls.length

    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.instances.mock.calls.length).toBe(calls)

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(5_000)
    expect(api.instances.mock.calls.length).toBeGreaterThan(calls)
    wrapper.unmount()
  })

  it('tras 10 minutos sin conexión se detiene y ofrece seguir esperando', async () => {
    const wrapper = mountPanel()
    await generateAndClose(wrapper)

    await vi.advanceTimersByTimeAsync(10 * 60_000 + 5_000)
    await flushPromises()

    expect(wrapper.text()).toContain('No se detectó ninguna conexión')
    const calls = api.instances.mock.calls.length
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.instances.mock.calls.length).toBe(calls)

    await wrapper.get('[data-test="link-keep-waiting"]').trigger('click')
    await vi.advanceTimersByTimeAsync(5_000)
    expect(api.instances.mock.calls.length).toBeGreaterThan(calls)
    wrapper.unmount()
  })

  it('un fallo de red al consultar no corta la espera', async () => {
    const wrapper = mountPanel()
    await generateAndClose(wrapper)
    api.instances.mockRejectedValueOnce(new Error('sin red'))
    await vi.advanceTimersByTimeAsync(5_000)

    api.instances.mockResolvedValue([NEW_INSTANCE])
    await vi.advanceTimersByTimeAsync(5_000)
    await flushPromises()

    expect(wrapper.find('[data-test="link-step-linked"]').exists()).toBe(true)
  })

  it('sin tokens.manage no ofrece generar ni revocar, pero sí lista los tokens', () => {
    const wrapper = mountPanel([PENDING], false, false)

    expect(wrapper.find('[data-test="token-create"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="token-revoke"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('tarea de Soporte')
    expect(wrapper.text()).toContain('Vigente')
  })
})
