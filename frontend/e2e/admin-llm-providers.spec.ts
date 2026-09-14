import { expect, test } from '@playwright/test'
import { loginAsAdmin } from './helpers'

/**
 * E2E autenticado de `/admin/proveedores-ia` contra el backend real (sin
 * mocks de red): login, listado de proveedores, y prueba de credencial
 * de Claude con `local_session` — no requiere ninguna API key, así que
 * corre igual en cualquier máquina con el CLI logueado.
 */
test.describe('Administración de proveedores de IA', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
  })

  test('lista los proveedores soportados', async ({ page }) => {
    await page.goto('/admin/proveedores-ia')

    await expect(page.getByRole('heading', { name: 'Proveedores de IA' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Claude (Anthropic)' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Gemini (Google)' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'OpenAI' })).toBeVisible()
  })

  test('prueba la credencial de Claude con local_session', async ({ page }) => {
    // El CLI local lanza un subproceso real de `claude`; más lento que el
    // resto de la interacción con la UI.
    test.setTimeout(45000)
    await page.goto('/admin/proveedores-ia')

    const claudeCard = page.locator('article', {
      has: page.getByRole('heading', { name: 'Claude (Anthropic)' }),
    })
    await claudeCard.getByRole('button', { name: /Editar|Configurar/ }).click()

    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Tipo de credencial').selectOption('local_session')
    await expect(dialog.getByText('Claude usará el login local de este equipo.')).toBeVisible()

    // Sin catálogo de modelos, `local_session` exige un ID a mano antes
    // de poder probar la credencial (comportamiento real del backend).
    await dialog.getByLabel('Modelo de chat').fill('claude-haiku-4-5')
    await dialog.getByLabel('Modelo de títulos').fill('claude-haiku-4-5')

    await dialog.getByRole('button', { name: 'Probar credencial' }).click()

    // El contrato estable es "el backend respondió con un detalle": la
    // prueba real depende del CLI local y de su cuota, que puede estar
    // agotada sin que la interfaz tenga un bug.
    const detail = dialog.getByTestId('provider-test-detail')
    await expect(detail).toBeVisible({ timeout: 30000 })
    await expect(detail).toHaveText(/\S/)
  })
})
