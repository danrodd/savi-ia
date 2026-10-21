import { describe, expect, it } from 'vitest'
import { AuthRequestError } from '../services/authService'
import {
  DATABASE_DISABLED_MESSAGE,
  DATABASE_UNREACHABLE_MESSAGE,
  GENERIC_LOGIN_MESSAGE,
  loginErrorMessage,
  NETWORK_LOGIN_MESSAGE,
  UNKNOWN_DATABASE_MESSAGE,
} from '../utils/loginErrors'

describe('loginErrorMessage', () => {
  it('un código de cliente inexistente señala el dato que hay que revisar', () => {
    const err = new AuthRequestError('No encontramos ese cliente.', 401, 'unknown_database')

    expect(loginErrorMessage(err)).toBe(UNKNOWN_DATABASE_MESSAGE)
    expect(UNKNOWN_DATABASE_MESSAGE).toBe(
      'No encontramos ese cliente. Revise el código después de la @.',
    )
  })

  it('un cliente registrado pero desactivado se explica aparte', () => {
    const err = new AuthRequestError('Ese cliente está desactivado', 401, 'database_disabled')

    expect(loginErrorMessage(err)).toBe(DATABASE_DISABLED_MESSAGE)
    expect(DATABASE_DISABLED_MESSAGE).toBe(
      'Ese cliente está desactivado en SAVI. Avise a su administrador.',
    )
  })

  it('un cliente activo sin conexión es un 503 que no se confunde con SAVI caído', () => {
    const err = new AuthRequestError('No pudimos conectar', 503, 'database_unreachable')

    expect(loginErrorMessage(err)).toBe(DATABASE_UNREACHABLE_MESSAGE)
    expect(DATABASE_UNREACHABLE_MESSAGE).toBe(
      'No pudimos conectar con la base de ese cliente. Pruebe de nuevo en unos minutos o avise a su administrador.',
    )
    // Un 503 sin código sigue siendo "SAVI no responde".
    expect(loginErrorMessage(new AuthRequestError('HTTP 503', 503))).toMatch(/SAVI no está/)
  })

  it('credenciales malas no revelan cuál dato falló', () => {
    const err = new AuthRequestError('Usuario o contraseña inválidos', 401)

    expect(loginErrorMessage(err)).toBe(GENERIC_LOGIN_MESSAGE)
    expect(GENERIC_LOGIN_MESSAGE).toBe(
      'No pudimos entrar. Revise el usuario, la contraseña y el código del cliente.',
    )
  })

  it('un texto técnico de HTTP nunca llega a la pantalla', () => {
    const err = new AuthRequestError('HTTP 401 Unauthorized', 401)

    expect(loginErrorMessage(err)).not.toMatch(/HTTP/)
  })

  it('cuenta deshabilitada y demasiados intentos conservan el motivo del backend', () => {
    expect(loginErrorMessage(new AuthRequestError('El usuario está deshabilitado', 403))).toBe(
      'El usuario está deshabilitado',
    )
    expect(
      loginErrorMessage(new AuthRequestError('Demasiados intentos. Pruebe en 60 segundos.', 429)),
    ).toBe('Demasiados intentos. Pruebe en 60 segundos.')
  })

  it('sin conexión explica que es un problema de red', () => {
    expect(loginErrorMessage(new TypeError('Failed to fetch'))).toBe(NETWORK_LOGIN_MESSAGE)
  })
})
