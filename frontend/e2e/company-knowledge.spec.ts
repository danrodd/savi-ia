import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { type APIRequestContext, expect, test } from '@playwright/test'
import { API_BASE_URL, activateStableProvider, loginAsAdmin } from './helpers'

/**
 * E2E de documentos de la empresa contra el backend real y Claude.
 *
 * El fixture es SINTÉTICO (sin datos de ningún cliente) y trae una regla
 * inventada e inconfundible: "tope de descuento sin autorización 7,5%
 * (POL-DSC-19)". Si SAVI responde 7,5 citando la fuente, la respuesta salió
 * del documento y no del modelo.
 */
const FIXTURE = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  'fixtures',
  'politica-descuentos.pdf',
)
const TITLE = 'politica-descuentos'
/** Usuario real no administrador del ERP de desarrollo (farmacias_similares). */
const NON_ADMIN_LOGIN = 'FSCOGL17'

async function adminHeaders(request: APIRequestContext): Promise<Record<string, string>> {
  const login = await request.post(`${API_BASE_URL}/auth/login`, {
    data: { login: 'admin', password: '123' },
  })
  const { access_token: token } = (await login.json()) as { access_token: string }
  return { Authorization: `Bearer ${token}` }
}

/** Borra restos de corridas anteriores: el backend rechaza duplicados por contenido. */
async function removeFixtureDocuments(request: APIRequestContext): Promise<void> {
  const headers = await adminHeaders(request)
  const list = await request.get(`${API_BASE_URL}/admin/company-documents`, { headers })
  for (const doc of (await list.json()) as { id: string; title: string }[]) {
    if (doc.title === TITLE) {
      await request.delete(`${API_BASE_URL}/admin/company-documents/${doc.id}`, { headers })
    }
  }
}

test.describe('Conocimiento de la empresa', () => {
  test.describe.configure({ mode: 'serial' })

  test.beforeAll(async ({ request }) => {
    await activateStableProvider(request)
    await removeFixtureDocuments(request)
  })

  test.afterAll(async ({ request }) => {
    await removeFixtureDocuments(request)
  })

  test('sube un PDF, queda listo y la búsqueda de prueba lo encuentra', async ({ page }) => {
    test.setTimeout(180_000)
    await loginAsAdmin(page)
    await page.goto('/admin/conocimiento')
    await expect(page.getByRole('heading', { name: 'Conocimiento de la empresa' })).toBeVisible()

    await page.getByRole('button', { name: 'Subir documentos' }).click()
    await page.getByLabel('Elegir archivos').setInputFiles(FIXTURE)
    await expect(page.getByLabel(`Título de ${TITLE}.pdf`)).toHaveValue(TITLE)
    await page.getByRole('button', { name: 'Subir (1)' }).click()
    await expect(page.getByText('Subido. Se está procesando.')).toBeVisible({ timeout: 30_000 })
    await page.getByRole('contentinfo').getByRole('button', { name: 'Cerrar' }).click()

    const row = page.getByRole('row', { name: new RegExp(TITLE) })
    await expect(row.getByText('Listo')).toBeVisible({ timeout: 120_000 })

    await page.getByRole('button', { name: 'Probar búsqueda' }).click()
    await page
      .getByPlaceholder('¿Cuál es el tope de descuento?')
      .fill('tope de descuento sin autorización')
    await page.getByRole('button', { name: 'Probar', exact: true }).click()
    await expect(page.locator('.doctest__hit').first()).toContainText(TITLE, { timeout: 30_000 })
  })

  test('un usuario sin permiso no lo encuentra en la búsqueda de prueba', async ({
    page,
    request,
  }) => {
    const headers = await adminHeaders(request)
    const list = (await (
      await request.get(`${API_BASE_URL}/admin/company-documents`, { headers })
    ).json()) as { id: string; title: string }[]
    const doc = list.find((d) => d.title === TITLE)
    expect(doc).toBeDefined()
    await request.patch(`${API_BASE_URL}/admin/company-documents/${doc?.id}`, {
      headers,
      data: { visibility: 'admins', modules: [] },
    })

    await loginAsAdmin(page)
    await page.goto('/admin/conocimiento')
    await expect(page.getByRole('row', { name: new RegExp(TITLE) })).toContainText(
      'Solo administradores',
    )

    await page.getByRole('button', { name: 'Probar búsqueda' }).click()
    await page
      .getByPlaceholder('¿Cuál es el tope de descuento?')
      .fill('tope de descuento sin autorización')
    await page.getByPlaceholder('Código del ERP').fill(NON_ADMIN_LOGIN)
    await page.getByRole('button', { name: 'Probar', exact: true }).click()

    const result = page.locator('.doctest__result')
    await expect(result).toContainText('Documentos que este usuario no puede consultar', {
      timeout: 30_000,
    })
    await expect(result).toContainText(`${TITLE} — Solo administradores`)
    await expect(page.locator('.doctest__hit')).toHaveCount(0)

    await request.patch(`${API_BASE_URL}/admin/company-documents/${doc?.id}`, {
      headers,
      data: { visibility: 'all' },
    })
  })

  test('el chat responde con el documento, cita la fuente y abre el original', async ({ page }) => {
    test.setTimeout(180_000)
    await loginAsAdmin(page)
    await page.goto('/')

    const composer = page.getByPlaceholder('Pregúntale a SAVI…')
    await composer.fill(
      'Según los documentos de la empresa, ¿cuál es el tope de descuento que un cajero puede dar sin autorización?',
    )
    await page.getByRole('button', { name: 'Enviar' }).click()
    // Primero que arranque el streaming: si no, "Detener" tiene 0 elementos
    // ANTES de empezar y la espera siguiente pasaría en el acto.
    await expect(page.getByRole('button', { name: 'Detener' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Detener' })).toHaveCount(0, { timeout: 150_000 })

    const answer = page.locator('.assistant-message').last()
    await expect(answer.locator('.assistant-message__content')).toContainText('7,5')
    // Sin referencias crudas: las válidas se ven como número superíndice.
    await expect(answer.locator('.assistant-message__content')).not.toContainText('[D')

    const sources = answer.locator('.sources')
    await expect(sources).toContainText('Fuentes')
    const link = sources.getByRole('button', { name: new RegExp(`Abrir ${TITLE}`) })
    await expect(link).toBeVisible()

    // El negrita del modelo no se rompe al insertar la marca de cita.
    await expect(answer.locator('.assistant-message__content')).not.toContainText('**')

    // Lo verificable de SAVI: la descarga protegida responde el PDF y se abre
    // una pestaña. Chromium headless no tiene visor de PDF (lo descarga en vez
    // de navegar), así que la URL de la pestaña no es una señal confiable acá.
    const download = page.waitForResponse(
      (res) => res.url().includes('/company-documents/') && res.url().includes('/file'),
    )
    const popupEvent = page.waitForEvent('popup')
    await link.click()
    const response = await download
    expect(response.status()).toBe(200)
    expect(response.headers()['content-type']).toContain('application/pdf')
    expect(response.headers()['x-content-type-options']).toBe('nosniff')
    await popupEvent
  })
})
