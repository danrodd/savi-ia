import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthRequestError } from '../services/authService'
import type { LoginResult, MfaChallenge, TokenResponse } from '../types'

const service = vi.hoisted(() => ({
  login: vi.fn(),
  mfaSetup: vi.fn(),
  mfaConfirm: vi.fn(),
  mfaVerify: vi.fn(),
  refresh: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
}))

vi.mock('../services/authService', async (importOriginal) => {
  const original = await importOriginal<typeof import('../services/authService')>()
  return { ...original, authService: service }
})

vi.mock('@/modules/permisos', () => ({
  usePermisosStore: () => ({ cargarBootstrap: vi.fn().mockResolvedValue(undefined) }),
}))

vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,QR') },
}))

// Importados después de los mocks.
import MfaPanel from '../components/MfaPanel.vue'
import { useAuthStore } from '../stores/authStore'
import { isMfaExpired, loginErrorMessage } from '../utils/loginErrors'

const TOKENS: TokenResponse = {
  status: 'authenticated',
  access_token: 'access',
  refresh_token: 'refresh',
  token_type: 'Bearer',
  expires_in: 900,
  user: { id: 1, login: 'ADMIN', full_name: 'Admin', is_admin: true },
}

const CHALLENGE: MfaChallenge = { status: 'mfa_required', mfa_token: 'mfa-tok', expires_in: 300 }
const SETUP_CHALLENGE: MfaChallenge = {
  status: 'mfa_setup_required',
  mfa_token: 'setup-tok',
  expires_in: 600,
}

function rejected(status: number, errorCode?: string): AuthRequestError {
  return new AuthRequestError('detalle', status, errorCode)
}

beforeEach(() => {
  setActivePinia(createPinia())
  window.localStorage.clear()
  vi.clearAllMocks()
})

describe('authStore con segundo factor', () => {
  it('un desafío NO abre sesión ni guarda tokens', async () => {
    service.login.mockResolvedValue(CHALLENGE satisfies LoginResult)
    const store = useAuthStore()

    const pending = await store.login({ login: 'ADMIN', password: 'x' })

    expect(pending).toEqual(CHALLENGE)
    expect(store.isAuthenticated).toBe(false)
    expect(store.accessToken).toBeNull()
    expect(window.localStorage.length).toBe(0)
  })

  it('sin desafío el login sigue abriendo la sesión como siempre', async () => {
    service.login.mockResolvedValue(TOKENS)
    const store = useAuthStore()

    const pending = await store.login({ login: 'CAJERO', password: 'x' })

    expect(pending).toBeNull()
    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.login).toBe('ADMIN')
  })

  it('una respuesta anterior al segundo factor (sin `status`) también es una sesión', async () => {
    const { status: _status, ...legacy } = TOKENS
    service.login.mockResolvedValue(legacy)
    const store = useAuthStore()

    expect(await store.login({ login: 'A', password: 'x' })).toBeNull()
    expect(store.isAuthenticated).toBe(true)
  })

  it('verifyMfa y confirmMfaSetup abren la sesión recién con el código correcto', async () => {
    service.mfaVerify.mockResolvedValue(TOKENS)
    service.mfaConfirm.mockResolvedValue(TOKENS)
    const store = useAuthStore()

    await store.verifyMfa('mfa-tok', '123456')
    expect(service.mfaVerify).toHaveBeenCalledWith('mfa-tok', '123456')
    expect(store.isAuthenticated).toBe(true)

    store.clearSession()
    await store.confirmMfaSetup('setup-tok', '654321')
    expect(service.mfaConfirm).toHaveBeenCalledWith('setup-tok', '654321')
    expect(store.isAuthenticated).toBe(true)
  })

  it('un código inválido no deja sesión a medias', async () => {
    service.mfaVerify.mockRejectedValue(rejected(401, 'invalid_mfa_code'))
    const store = useAuthStore()

    await expect(store.verifyMfa('mfa-tok', '000000')).rejects.toBeInstanceOf(AuthRequestError)
    expect(store.isAuthenticated).toBe(false)
  })
})

describe('MfaPanel', () => {
  it('con el factor ya configurado pide el código y no genera un secreto', async () => {
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE } })
    await flushPromises()

    expect(service.mfaSetup).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="mfa-qr"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Verificación en dos pasos')
  })

  it('en el primer ingreso muestra el QR y la clave para cargar a mano', async () => {
    service.mfaSetup.mockResolvedValue({
      secret: 'ABCD2345ABCD2345',
      otpauth_uri: 'otpauth://totp/x',
    })
    const wrapper = mount(MfaPanel, { props: { challenge: SETUP_CHALLENGE } })
    await flushPromises()

    expect(service.mfaSetup).toHaveBeenCalledWith('setup-tok')
    expect(wrapper.get('[data-testid="mfa-qr"]').attributes('src')).toBe('data:image/png;base64,QR')
    expect(wrapper.get('[data-testid="mfa-secret"]').text()).toBe('ABCD2345ABCD2345')
  })

  it('un código correcto abre la sesión y avisa que terminó', async () => {
    service.mfaVerify.mockResolvedValue(TOKENS)
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE } })

    await wrapper.get('[data-testid="mfa-code"]').setValue('123 456')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    // Los espacios se descartan: lo pegan con el espacio que muestra la aplicación.
    expect(service.mfaVerify).toHaveBeenCalledWith('mfa-tok', '123456')
    expect(wrapper.emitted('done')).toHaveLength(1)
  })

  it('un código incorrecto muestra el aviso, limpia el campo y no termina', async () => {
    service.mfaVerify.mockRejectedValue(rejected(401, 'invalid_mfa_code'))
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE } })

    await wrapper.get('[data-testid="mfa-code"]').setValue('000000')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('El código no es válido')
    expect((wrapper.get('[data-testid="mfa-code"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.emitted('done')).toBeUndefined()
  })

  it('si el desafío venció vuelve al formulario con un aviso', async () => {
    service.mfaVerify.mockRejectedValue(rejected(401))
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE } })

    await wrapper.get('[data-testid="mfa-code"]').setValue('123456')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('cancel')?.[0]).toEqual([
      'La verificación venció. Volvé a iniciar sesión.',
    ])
  })

  it('no envía un código incompleto', async () => {
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE } })

    await wrapper.get('[data-testid="mfa-code"]').setValue('12')
    await wrapper.get('form').trigger('submit')

    expect(service.mfaVerify).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('6 dígitos')
  })

  it('el primer ingreso confirma con el primer código', async () => {
    service.mfaSetup.mockResolvedValue({ secret: 'ABCD2345ABCD2345', otpauth_uri: 'otpauth://x' })
    service.mfaConfirm.mockResolvedValue(TOKENS)
    const wrapper = mount(MfaPanel, { props: { challenge: SETUP_CHALLENGE } })
    await flushPromises()

    await wrapper.get('[data-testid="mfa-code"]').setValue('654321')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(service.mfaConfirm).toHaveBeenCalledWith('setup-tok', '654321')
    expect(wrapper.emitted('done')).toHaveLength(1)
  })
})

describe('mensajes de error del segundo factor', () => {
  it('distingue un código incorrecto de un desafío vencido', () => {
    expect(isMfaExpired(rejected(401, 'invalid_mfa_code'))).toBe(false)
    expect(isMfaExpired(rejected(401))).toBe(true)
    expect(isMfaExpired(rejected(429))).toBe(false)
    expect(isMfaExpired(new Error('red'))).toBe(false)
  })

  it('traduce el código inválido y deja pasar el mensaje del backend en 403 y 429', () => {
    expect(loginErrorMessage(rejected(401, 'invalid_mfa_code'))).toContain('El código no es válido')
    expect(
      loginErrorMessage(new AuthRequestError('Pedile a un administrador', 403, 'mfa_unavailable')),
    ).toBe('Pedile a un administrador')
  })
})
