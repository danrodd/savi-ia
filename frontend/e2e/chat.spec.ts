import { expect, test } from '@playwright/test'
import { activateStableProvider, loginAsAdmin } from './helpers'

/**
 * E2E autenticado del chat contra el backend real (sin mocks de red ni
 * de stream). Activa Claude con `local_session` antes de correr: no
 * depende de qué proveedor haya dejado activo un administrador ni de la
 * cuota de una API key de terceros (Gemini reintenta con backoff ante
 * saturación — ver `INFORME_AVANCE_PROVEEDORES_IA.md` — y una key de
 * pruebas agotada dejaría este test flaky sin que sea un bug real).
 */
test.describe('Chat', () => {
  test.beforeAll(async ({ request }) => {
    await activateStableProvider(request)
  })

  test('envía un mensaje y recibe una respuesta completa del asistente', async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/')

    const composer = page.getByPlaceholder('Pregúntale a SAVI…')
    await expect(composer).toBeVisible()
    await composer.fill('Decime en una frase muy corta qué es SAVI.')
    await page.getByRole('button', { name: 'Enviar' }).click()

    // El mensaje del usuario aparece de inmediato en el hilo.
    await expect(page.locator('.user-message').last()).toContainText(
      'Decime en una frase muy corta qué es SAVI.',
    )

    // El streaming arrancó (aparece "Detener") y luego el turno termina
    // (desaparece — el botón "Enviar" vuelve, disabled porque el input
    // quedó vacío tras el envío, así que no sirve como señal por sí solo).
    await expect(page.getByRole('button', { name: 'Detener' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Detener' })).toHaveCount(0, {
      timeout: 90000,
    })

    const assistantMessage = page.locator('.assistant-message').last()
    await expect(assistantMessage).toBeVisible()
    await expect(assistantMessage.locator('.assistant-message__content')).not.toBeEmpty()
    await expect(assistantMessage.locator('.assistant-message__error')).toHaveCount(0)
  })
})
