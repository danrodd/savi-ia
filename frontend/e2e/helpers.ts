import type { APIRequestContext, Page } from '@playwright/test'

/** Debe coincidir con `VITE_API_BASE_URL` (`.env`) y con el backend real. */
export const API_BASE_URL = 'http://127.0.0.1:8000'

/**
 * Login real contra el backend (sin mocks): completa el formulario y
 * espera a que el guard nos saque de `/login`. Las credenciales son las
 * del ERP de desarrollo (admin/123, ver CLAUDE.md).
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Usuario').fill('admin')
  await page.getByLabel('Contraseña').fill('123')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 })
}

/**
 * Activa Claude con `local_session` vía la API de administración, sin
 * pasar por la UI. Se usa como setup de specs que necesitan un turno de
 * chat determinístico: no depende de qué proveedor haya dejado activo un
 * administrador, ni de la cuota de una API key externa.
 */
export async function activateStableProvider(request: APIRequestContext): Promise<void> {
  const login = await request.post(`${API_BASE_URL}/auth/login`, {
    data: { login: 'admin', password: '123' },
  })
  const { access_token: token } = (await login.json()) as { access_token: string }
  const headers = { Authorization: `Bearer ${token}` }

  await request.put(`${API_BASE_URL}/admin/llm-providers/claude`, {
    headers,
    data: {
      credential_kind: 'local_session',
      chat_model: 'claude-sonnet-4-6',
      title_model: 'claude-haiku-4-5',
    },
  })
  await request.post(`${API_BASE_URL}/admin/llm-providers/claude/activate`, { headers })
}
