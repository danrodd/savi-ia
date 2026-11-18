import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
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

/** Escribe el código en las casillas: al completarse, el panel lo envía solo. */
async function typeCode(wrapper: VueWrapper, code: string): Promise<void> {
  const cells = wrapper.findAll('[data-test="two-factor"] input')
  for (const [i, digit] of code.split('').entries()) {
    await cells[i]?.setValue(digit)
  }
  await flushPromises()
}

describe('MfaPanel', () => {
  it('con el factor ya configurado pide el código y no genera un secreto', async () => {
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE } })
    await flushPromises()

    expect(service.mfaSetup).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="two-factor-qr"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Código de verificación')
    expect(wrapper.text()).toContain('Administración → Seguridad')
  })

  it('en el primer ingreso muestra el QR y la clave para cargar a mano', async () => {
    service.mfaSetup.mockResolvedValue({
      secret: 'ABCD2345ABCD2345',
      otpauth_uri: 'otpauth://totp/x',
    })
    const wrapper = mount(MfaPanel, { props: { challenge: SETUP_CHALLENGE } })
    await flushPromises()

    expect(service.mfaSetup).toHaveBeenCalledWith('setup-tok')
    expect(wrapper.get('[data-test="two-factor-qr"]').attributes('src')).toBe(
      'data:image/png;base64,QR',
    )
    await wrapper.get('[data-test="two-factor-show-key"]').trigger('click')
    expect(wrapper.get('[data-test="two-factor-secret"]').text()).toBe('ABCD 2345 ABCD 2345')
  })

  it('un código correcto abre la sesión sin un clic extra', async () => {
    service.mfaVerify.mockResolvedValue(TOKENS)
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE }, attachTo: document.body })

    await typeCode(wrapper, '123456')

    expect(service.mfaVerify).toHaveBeenCalledWith('mfa-tok', '123456')
    expect(wrapper.emitted('done')).toHaveLength(1)
    wrapper.unmount()
  })

  it('un código incorrecto muestra el aviso, limpia las casillas y no termina', async () => {
    service.mfaVerify.mockRejectedValue(rejected(401, 'invalid_mfa_code'))
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE }, attachTo: document.body })

    await typeCode(wrapper, '000000')

    expect(wrapper.get('[role="alert"]').text()).toContain('El código no es válido')
    const cells = wrapper.findAll('[data-test="two-factor"] input')
    expect(cells.every((c) => (c.element as HTMLInputElement).value === '')).toBe(true)
    expect(wrapper.emitted('done')).toBeUndefined()
    wrapper.unmount()
  })

  it('si el desafío venció vuelve al formulario con un aviso', async () => {
    service.mfaVerify.mockRejectedValue(rejected(401))
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE }, attachTo: document.body })

    await typeCode(wrapper, '123456')

    expect(wrapper.emitted('cancel')?.[0]).toEqual([
      'La verificación venció. Vuelva a iniciar sesión.',
    ])
    wrapper.unmount()
  })

  it('no envía un código incompleto', async () => {
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE }, attachTo: document.body })

    await typeCode(wrapper, '12')

    expect(service.mfaVerify).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('el primer ingreso confirma con el primer código', async () => {
    service.mfaSetup.mockResolvedValue({ secret: 'ABCD2345ABCD2345', otpauth_uri: 'otpauth://x' })
    service.mfaConfirm.mockResolvedValue(TOKENS)
    const wrapper = mount(MfaPanel, {
      props: { challenge: SETUP_CHALLENGE },
      attachTo: document.body,
    })
    await flushPromises()

    await typeCode(wrapper, '654321')

    expect(service.mfaConfirm).toHaveBeenCalledWith('setup-tok', '654321')
    expect(wrapper.emitted('done')).toHaveLength(1)
    wrapper.unmount()
  })

  it('volver cancela el segundo paso', async () => {
    const wrapper = mount(MfaPanel, { props: { challenge: CHALLENGE } })
    await wrapper.get('.ui-2fa__back').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
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
      loginErrorMessage(new AuthRequestError('Pídale a un administrador', 403, 'mfa_unavailable')),
    ).toBe('Pídale a un administrador')
  })
})
