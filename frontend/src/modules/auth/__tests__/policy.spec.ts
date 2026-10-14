import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TokenResponse } from '../types'

const service = vi.hoisted(() => ({
  login: vi.fn(),
  policy: vi.fn(),
  refresh: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
  mfaSetup: vi.fn(),
  mfaConfirm: vi.fn(),
  mfaVerify: vi.fn(),
}))

vi.mock('../services/authService', async (importOriginal) => {
  const original = await importOriginal<typeof import('../services/authService')>()
  return { ...original, authService: service }
})

vi.mock('@/modules/permisos', () => ({
  usePermisosStore: () => ({ cargarBootstrap: vi.fn().mockResolvedValue(undefined) }),
}))

import { useAuthStore } from '../stores/authStore'

const ADMIN: TokenResponse = {
  status: 'authenticated',
  access_token: 'access',
  refresh_token: 'refresh',
  token_type: 'Bearer',
  expires_in: 900,
  user: { id: 1, login: 'ADMIN', full_name: 'Admin', is_admin: true },
}

beforeEach(() => {
  setActivePinia(createPinia())
  window.localStorage.clear()
  vi.clearAllMocks()
})

describe('instalación bloqueada por SEO Group', () => {
  it('con la configuración bloqueada la persona deja de verse como administradora', async () => {
    service.login.mockResolvedValue(ADMIN)
    service.policy.mockResolvedValue({ config_locked: true })
    const store = useAuthStore()

    await store.login({ login: 'ADMIN', password: 'x' })

    expect(store.configLocked).toBe(true)
    expect(store.user?.is_admin).toBe(false)
  })

  it('sin bloqueo conserva el rol', async () => {
    service.login.mockResolvedValue(ADMIN)
    service.policy.mockResolvedValue({ config_locked: false })
    const store = useAuthStore()

    await store.login({ login: 'ADMIN', password: 'x' })

    expect(store.configLocked).toBe(false)
    expect(store.user?.is_admin).toBe(true)
  })

  it('si no se puede consultar la política, no bloquea (el backend decide)', async () => {
    service.login.mockResolvedValue(ADMIN)
    service.policy.mockRejectedValue(new Error('sin red'))
    const store = useAuthStore()

    await store.login({ login: 'ADMIN', password: 'x' })

    expect(store.configLocked).toBe(false)
    expect(store.user?.is_admin).toBe(true)
  })

  it('al cerrar sesión se descarta el bloqueo', async () => {
    service.login.mockResolvedValue(ADMIN)
    service.policy.mockResolvedValue({ config_locked: true })
    const store = useAuthStore()
    await store.login({ login: 'ADMIN', password: 'x' })

    store.clearSession()

    expect(store.configLocked).toBe(false)
  })

  it('el rol reducido se persiste para que una recarga no lo muestre como admin un instante', async () => {
    service.login.mockResolvedValue(ADMIN)
    service.policy.mockResolvedValue({ config_locked: true })
    await useAuthStore().login({ login: 'ADMIN', password: 'x' })

    const stored = JSON.parse(
      window.localStorage.getItem(
        [...Array(window.localStorage.length).keys()]
          .map((i) => window.localStorage.key(i) ?? '')
          .find((k) => k.toLowerCase().includes('user')) ?? '',
      ) ?? '{}',
    ) as { is_admin?: boolean }
    expect(stored.is_admin).toBe(false)
  })
})
