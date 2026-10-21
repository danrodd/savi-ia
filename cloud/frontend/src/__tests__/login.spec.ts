import { OtpInput } from '@savi/ui'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ApiError } from '@/lib/http'

const authApi = vi.hoisted(() => ({
  login: vi.fn(),
  beginSetup: vi.fn(),
  mfa: vi.fn(),
  confirmSetup: vi.fn(),
  refresh: vi.fn(),
  logout: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ authApi, consoleApi: {} }))
vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,') },
}))

import LoginView from '@/views/LoginView.vue'

const SESSION = {
  access_token: 'tok',
  user: { id: 'u1', email: 'ana@seo.example', full_name: 'Ana', role: 'admin', permissions: [] },
}

async function mountLogin() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: LoginView },
      { path: '/', name: 'overview', component: { template: '<div>resumen</div>' } },
    ],
  })
  await router.push('/login')
  const wrapper = mount(LoginView, { global: { plugins: [router] }, attachTo: document.body })
  return { wrapper, router }
}

async function enterCredentials(wrapper: Awaited<ReturnType<typeof mountLogin>>['wrapper']) {
  await wrapper.get('input[type="email"]').setValue('ana@seo.example')
  await wrapper.get('input[type="password"]').setValue('temporal-123')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

async function completeCode(
  wrapper: Awaited<ReturnType<typeof mountLogin>>['wrapper'],
  code: string,
) {
  wrapper.findComponent(OtpInput).vm.$emit('complete', code)
  await flushPromises()
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  document.body.innerHTML = ''
  authApi.beginSetup.mockResolvedValue({
    secret: 'JBSWY3DPEHPK3PXP',
    otpauth_uri: 'otpauth://totp/x',
  })
  authApi.mfa.mockResolvedValue(SESSION)
  authApi.confirmSetup.mockResolvedValue(SESSION)
})

describe('ingreso a la consola', () => {
  it('sin datos marca los campos y no llama al API', async () => {
    const { wrapper } = await mountLogin()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(authApi.login).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Ingrese un correo válido.')
    expect(wrapper.text()).toContain('Ingrese su contraseña.')
  })

  it('con el segundo factor configurado pide el código y entra al completarlo', async () => {
    authApi.login.mockResolvedValue({
      status: 'mfa_required',
      token: 'mfa-tok',
      must_change_password: false,
    })
    const { wrapper, router } = await mountLogin()

    await enterCredentials(wrapper)
    expect(wrapper.text()).toContain('Código de verificación')

    await completeCode(wrapper, '123456')

    expect(authApi.mfa).toHaveBeenCalledWith('mfa-tok', '123456')
    expect(router.currentRoute.value.name).toBe('overview')
  })

  it('un código rechazado muestra el error y deja reintentar', async () => {
    authApi.login.mockResolvedValue({
      status: 'mfa_required',
      token: 'mfa-tok',
      must_change_password: false,
    })
    authApi.mfa.mockRejectedValueOnce(
      new ApiError(401, 'invalid_mfa_code', 'El código no es válido.'),
    )
    const { wrapper, router } = await mountLogin()

    await enterCredentials(wrapper)
    await completeCode(wrapper, '000000')

    expect(wrapper.text()).toContain('El código no es válido.')
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.findComponent(OtpInput).props('modelValue')).toBe('')
  })
})

describe('primer ingreso', () => {
  beforeEach(() => {
    authApi.login.mockResolvedValue({
      status: 'mfa_setup_required',
      token: 'setup-tok',
      must_change_password: true,
    })
  })

  it('pide la contraseña nueva antes que el código y no envía nada todavía', async () => {
    const { wrapper } = await mountLogin()

    await enterCredentials(wrapper)

    expect(wrapper.text()).toContain('Elija su contraseña')
    expect(wrapper.findComponent(OtpInput).exists()).toBe(false)
    expect(authApi.confirmSetup).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Al menos 12 caracteres')
  })

  it('no avanza con una contraseña que no cumple o que no coincide', async () => {
    const { wrapper } = await mountLogin()
    await enterCredentials(wrapper)

    const [password, repeat] = wrapper.findAll('input[type="password"]')
    await password?.setValue('corta')
    await repeat?.setValue('otra')
    await wrapper.get('[data-test="password-continue"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Las contraseñas no coinciden.')
    expect(wrapper.text()).toContain('Falta: al menos 12 caracteres.')
    expect(wrapper.findComponent(OtpInput).exists()).toBe(false)
  })

  it('con la contraseña válida muestra el QR y envía todo al completar el código', async () => {
    const { wrapper, router } = await mountLogin()
    await enterCredentials(wrapper)

    const [password, repeat] = wrapper.findAll('input[type="password"]')
    await password?.setValue('Consola-segura-2026')
    await repeat?.setValue('Consola-segura-2026')
    await wrapper.get('[data-test="password-continue"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Verificación en dos pasos')
    expect(wrapper.text()).toContain('JBSWY3DPEHPK3PXP')

    await completeCode(wrapper, '654321')

    expect(authApi.confirmSetup).toHaveBeenCalledWith('setup-tok', '654321', 'Consola-segura-2026')
    expect(router.currentRoute.value.name).toBe('overview')
  })

  it('si el servidor rechaza la contraseña vuelve a ese paso con su mensaje', async () => {
    authApi.confirmSetup.mockRejectedValueOnce(
      new ApiError(422, 'weak_password', 'Esa contraseña es demasiado común.'),
    )
    const { wrapper } = await mountLogin()
    await enterCredentials(wrapper)
    const [password, repeat] = wrapper.findAll('input[type="password"]')
    await password?.setValue('Consola-segura-2026')
    await repeat?.setValue('Consola-segura-2026')
    await wrapper.get('[data-test="password-continue"]').trigger('click')
    await flushPromises()

    await completeCode(wrapper, '654321')

    expect(wrapper.text()).toContain('Elija su contraseña')
    expect(wrapper.text()).toContain('Esa contraseña es demasiado común.')
  })

  it('si venció la verificación vuelve al ingreso con un aviso', async () => {
    authApi.confirmSetup.mockRejectedValueOnce(
      new ApiError(401, 'invalid_session_token', 'El token venció.'),
    )
    const { wrapper } = await mountLogin()
    await enterCredentials(wrapper)
    const [password, repeat] = wrapper.findAll('input[type="password"]')
    await password?.setValue('Consola-segura-2026')
    await repeat?.setValue('Consola-segura-2026')
    await wrapper.get('[data-test="password-continue"]').trigger('click')
    await flushPromises()

    await completeCode(wrapper, '654321')

    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('la verificación venció')
  })
})
