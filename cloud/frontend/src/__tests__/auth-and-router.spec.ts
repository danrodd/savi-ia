import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '@/lib/api'
import type { StaffUser, TokenResponse } from '@/lib/types'
import { useAuthStore } from '@/stores/authStore'

vi.mock('@/lib/api', () => ({
  authApi: {
    login: vi.fn(),
    mfa: vi.fn(),
    beginSetup: vi.fn(),
    confirmSetup: vi.fn(),
    refresh: vi.fn(),
    logout: vi.fn(),
  },
  consoleApi: {},
}))

function user(role: StaffUser['role'], permissions: StaffUser['permissions']): StaffUser {
  return { id: 'u1', email: 'a@b.co', full_name: 'Ana', role, permissions }
}

function session(u: StaffUser): TokenResponse {
  return { access_token: 'tok', expires_in: 900, must_change_password: false, user: u }
}

describe('authStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('un solo refresh aunque lo pidan varios a la vez', async () => {
    vi.mocked(authApi.refresh).mockResolvedValue(session(user('admin', ['overview.read'])))
    const auth = useAuthStore()

    const results = await Promise.all([auth.refresh(), auth.refresh(), auth.refresh()])

    expect(authApi.refresh).toHaveBeenCalledTimes(1)
    expect(results).toEqual(['tok', 'tok', 'tok'])
    expect(auth.isAuthenticated).toBe(true)
  })

  it('si el refresh falla, limpia la sesión y devuelve null', async () => {
    vi.mocked(authApi.refresh).mockRejectedValue(new Error('401'))
    const auth = useAuthStore()
    auth.accessToken = 'viejo'
    auth.user = user('admin', [])

    expect(await auth.refresh()).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('restore intenta recuperar la sesión una sola vez', async () => {
    vi.mocked(authApi.refresh).mockRejectedValue(new Error('401'))
    const auth = useAuthStore()

    await auth.restore()
    await auth.restore()

    expect(authApi.refresh).toHaveBeenCalledTimes(1)
  })

  it('can() solo responde por los permisos que el backend informó', () => {
    const auth = useAuthStore()
    auth.user = user('comercial', ['clients.read', 'clients.write'])

    expect(auth.can('clients.write')).toBe(true)
    expect(auth.can('instances.manage')).toBe(false)
    expect(auth.can('audit.read')).toBe(false)
  })

  it('el primer ingreso pasa por la configuración del TOTP', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      status: 'mfa_setup_required',
      token: 'setup-token',
      must_change_password: true,
    })
    vi.mocked(authApi.beginSetup).mockResolvedValue({
      secret: 'ABC',
      otpauth_uri: 'otpauth://totp/x',
    })
    const auth = useAuthStore()

    const step = await auth.submitCredentials('a@b.co', 'temporal')

    expect(step).toMatchObject({ kind: 'setup', mustChangePassword: true, token: 'setup-token' })
    expect(auth.isAuthenticated).toBe(false) // sin TOTP no hay sesión
  })

  it('con TOTP activo pide el código y recién ahí abre la sesión', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      status: 'mfa_required',
      token: 'mfa-token',
      must_change_password: false,
    })
    vi.mocked(authApi.mfa).mockResolvedValue(session(user('soporte', ['clients.read'])))
    const auth = useAuthStore()

    const step = await auth.submitCredentials('a@b.co', 'clave')
    expect(step).toEqual({ kind: 'mfa', token: 'mfa-token' })
    expect(auth.isAuthenticated).toBe(false)

    await auth.submitMfa('mfa-token', '123456')
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user?.role).toBe('soporte')
  })

  it('logout limpia la sesión aunque el servidor ya no la reconozca', async () => {
    vi.mocked(authApi.logout).mockResolvedValue(undefined)
    const auth = useAuthStore()
    auth.accessToken = 'tok'
    auth.user = user('admin', [])

    await auth.logout()

    expect(auth.accessToken).toBeNull()
    expect(auth.user).toBeNull()
  })
})

describe('guards del router', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.resetModules()
  })

  async function load() {
    const { default: router } = await import('@/router')
    const { useAuthStore: store } = await import('@/stores/authStore')
    return { router, auth: store() }
  }

  it('sin sesión manda al login y recuerda a dónde iba', async () => {
    vi.mocked(authApi.refresh).mockRejectedValue(new Error('401'))
    const { router } = await load()

    await router.push('/clientes')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/clientes')
  })

  it('con sesión pero sin permiso vuelve al resumen', async () => {
    vi.mocked(authApi.refresh).mockResolvedValue(
      session(user('comercial', ['overview.read', 'clients.read'])),
    )
    const { router } = await load()

    await router.push('/auditoria')

    expect(router.currentRoute.value.name).toBe('overview')
  })

  it('con el permiso entra a la pantalla', async () => {
    vi.mocked(authApi.refresh).mockResolvedValue(
      session(user('admin', ['overview.read', 'audit.read'])),
    )
    const { router } = await load()

    await router.push('/auditoria')

    expect(router.currentRoute.value.name).toBe('audit')
  })

  it('con sesión activa el login redirige al resumen', async () => {
    vi.mocked(authApi.refresh).mockResolvedValue(session(user('admin', ['overview.read'])))
    const { router } = await load()

    await router.push('/login')

    expect(router.currentRoute.value.name).toBe('overview')
  })
})
