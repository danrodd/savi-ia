/**
 * Mensajes del formulario de inicio de sesión.
 *
 * El texto técnico del backend ("Usuario o contraseña inválidos", "HTTP 401
 * Unauthorized") no le dice a quien atiende clientes qué revisar. Acá se
 * traduce a qué dato corregir.
 */
import { AuthRequestError } from '../services/authService'

export const MISSING_CREDENTIALS_MESSAGE = 'Ingrese usuario y contraseña.'

export const UNKNOWN_DATABASE_MESSAGE =
  'No encontramos ese cliente. Revise el código después de la @.'

export const DATABASE_DISABLED_MESSAGE =
  'Ese cliente está desactivado en SAVI. Avise a su administrador.'

export const DATABASE_UNREACHABLE_MESSAGE =
  'No pudimos conectar con la base de ese cliente. Pruebe de nuevo en unos minutos o avise a su administrador.'

export const INVALID_MFA_CODE_MESSAGE =
  'El código no es válido. Revisá el de tu aplicación e intentá de nuevo.'

export const MFA_EXPIRED_MESSAGE = 'La verificación venció. Volvé a iniciar sesión.'

export const GENERIC_LOGIN_MESSAGE =
  'No pudimos entrar. Revise el usuario, la contraseña y el código del cliente.'

export const NETWORK_LOGIN_MESSAGE =
  'No pudimos conectarnos con SAVI. Revise su conexión e intente de nuevo.'

/**
 * ¿El error del segundo factor es que el desafío venció (o ya no sirve)? Entonces la persona
 * tiene que volver a empezar: reintentar el código no sirve de nada.
 */
export function isMfaExpired(err: unknown): boolean {
  return (
    err instanceof AuthRequestError && err.status === 401 && err.errorCode !== 'invalid_mfa_code'
  )
}

export function loginErrorMessage(err: unknown): string {
  if (err instanceof AuthRequestError) {
    // Por `errorCode` y antes que el status: el de "sin conexión" es un 503 y
    // no debe caer en el aviso genérico de "SAVI no está respondiendo".
    if (err.errorCode === 'unknown_database') return UNKNOWN_DATABASE_MESSAGE
    if (err.errorCode === 'database_disabled') return DATABASE_DISABLED_MESSAGE
    if (err.errorCode === 'database_unreachable') return DATABASE_UNREACHABLE_MESSAGE
    if (err.errorCode === 'invalid_mfa_code') return INVALID_MFA_CODE_MESSAGE
    // Cuenta deshabilitada o demasiados intentos: el backend ya explica el
    // motivo (con la espera, si corresponde) y no hay un dato que corregir.
    if (err.status === 403 || err.status === 429) return err.message
    if (err.status >= 500)
      return 'SAVI no está respondiendo en este momento. Pruebe de nuevo en unos minutos.'
    return GENERIC_LOGIN_MESSAGE
  }
  if (err instanceof TypeError) return NETWORK_LOGIN_MESSAGE
  return GENERIC_LOGIN_MESSAGE
}
