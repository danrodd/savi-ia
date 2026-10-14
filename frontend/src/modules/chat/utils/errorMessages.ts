/**
 * Qué mensaje de error ve cada persona.
 *
 * Un error del proveedor de IA ("La API key de OpenAI no es válida", "cargar
 * saldo en Google AI Studio") le sirve a quien administra SAVI, pero a quien
 * atiende clientes sólo le genera dudas y no puede hacer nada. Por eso el
 * detalle técnico queda para administradores y el resto ve un aviso simple
 * que dice a quién acudir.
 */

export const ASSISTANT_UNAVAILABLE_MESSAGE =
  'El asistente no está disponible en este momento. Avisale a tu administrador.'

export const ASSISTANT_FAILED_MESSAGE =
  'No pude completar la respuesta. Probá de nuevo en un momento.'

export interface ChatErrorInfo {
  message: string
  /** Categoría que manda el backend (`provider_error`, `internal_error`). */
  code?: string | null
}

/**
 * Respaldo para un backend que todavía no manda `code`: reconoce los textos de
 * credencial, saldo y cuota que ya conocemos.
 */
const PROVIDER_TEXT_HINT =
  /api[\s-]?key|credencial|cr[eé]ditos|saldo|cuota|oauth|proveedor|ai studio|anthropic|openai|gemini/i

export function isProviderError(error: ChatErrorInfo): boolean {
  if (error.code === 'provider_error') return true
  if (error.code) return false
  return PROVIDER_TEXT_HINT.test(error.message)
}

export function resolveChatErrorMessage(error: ChatErrorInfo, isAdmin: boolean): string {
  if (isAdmin) return error.message
  if (isProviderError(error)) return ASSISTANT_UNAVAILABLE_MESSAGE
  if (error.code === 'internal_error') return ASSISTANT_FAILED_MESSAGE
  return error.message
}
