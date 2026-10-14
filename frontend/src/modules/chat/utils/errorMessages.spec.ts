import { describe, expect, it } from 'vitest'
import {
  ASSISTANT_FAILED_MESSAGE,
  ASSISTANT_UNAVAILABLE_MESSAGE,
  resolveChatErrorMessage,
} from './errorMessages'

const TECHNICAL = 'La API key de OpenAI no es válida o no tiene permisos.'

describe('resolveChatErrorMessage', () => {
  it('el administrador conserva el detalle técnico', () => {
    expect(resolveChatErrorMessage({ message: TECHNICAL, code: 'provider_error' }, true)).toBe(
      TECHNICAL,
    )
  })

  it('un usuario común no ve el texto del proveedor', () => {
    const result = resolveChatErrorMessage({ message: TECHNICAL, code: 'provider_error' }, false)

    expect(result).toBe(ASSISTANT_UNAVAILABLE_MESSAGE)
    expect(result).not.toMatch(/API key|OpenAI/)
  })

  it('un error interno tampoco muestra el texto crudo a un usuario común', () => {
    expect(
      resolveChatErrorMessage(
        { message: 'relation "x" does not exist', code: 'internal_error' },
        false,
      ),
    ).toBe(ASSISTANT_FAILED_MESSAGE)
  })

  it('un mensaje ya pensado para todos (sin categoría) se muestra tal cual', () => {
    const message = 'No pude generar una respuesta para esa consulta.'

    expect(resolveChatErrorMessage({ message, code: null }, false)).toBe(message)
  })

  it('sin categoría reconoce por texto un error de saldo del proveedor', () => {
    const message =
      'La cuenta de Gemini no tiene créditos. Un administrador debe cargar saldo en Google AI Studio.'

    expect(resolveChatErrorMessage({ message }, false)).toBe(ASSISTANT_UNAVAILABLE_MESSAGE)
    expect(resolveChatErrorMessage({ message }, true)).toBe(message)
  })

  it('el aviso usa voseo', () => {
    expect(ASSISTANT_UNAVAILABLE_MESSAGE).toContain('Avisale')
  })
})
