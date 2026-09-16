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

  test('recargar a mitad de respuesta se reengancha y la respuesta termina', async ({ page }) => {
    // Turno completo del modelo: el default de 30 s no alcanza.
    test.setTimeout(240_000)

    await loginAsAdmin(page)
    await page.goto('/')

    await page.getByPlaceholder('Pregúntale a SAVI…').fill(
      'Listá 15 funcionalidades del ERP, cada una con dos frases de explicación.',
    )
    await page.getByRole('button', { name: 'Enviar' }).click()

    // Hay que esperar la URL de la conversación: sin ella el reload vuelve a
    // `/` y no habría nada a lo que reengancharse.
    await expect(page).toHaveURL(/\/c\/[0-9a-f-]+$/, { timeout: 30_000 })
    await expect(page.getByRole('button', { name: 'Detener' })).toBeVisible()

    await page.reload()

    // Esta es la prueba: tras el reload la interfaz vuelve a mostrar "Detener",
    // o sea que encontró el turno todavía vivo y se enganchó a él. Antes el
    // reload mataba la generación y acá no habría más que media frase.
    await expect(page.getByRole('button', { name: 'Detener' })).toBeVisible({
      timeout: 30_000,
    })
    await expect(page.getByRole('button', { name: 'Detener' })).toHaveCount(0, {
      timeout: 180_000,
    })

    const assistantMessage = page.locator('.assistant-message').last()
    await expect(assistantMessage.locator('.assistant-message__content')).not.toBeEmpty()
    await expect(assistantMessage.locator('.assistant-message__error')).toHaveCount(0)
  })
})
