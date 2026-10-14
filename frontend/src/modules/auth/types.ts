/** Base del ERP con la que se inició sesión. */
export interface SessionDatabase {
  id: string
  code: string
  name: string
}

export interface AuthUser {
  id: number
  login: string
  full_name: string
  is_admin: boolean
  /**
   * Opcional: una sesión guardada antes de este campo no lo trae hasta el
   * próximo refresh. El `id` solo identifica a la persona junto con esta
   * base (se repite entre clientes).
   */
  erp_database?: SessionDatabase | null
}

export interface TokenResponse {
  /** Ausente en respuestas anteriores al segundo factor. */
  status?: 'authenticated'
  access_token: string
  refresh_token: string
  token_type: 'Bearer'
  expires_in: number
  user: AuthUser
}

/**
 * El login verificó la contraseña pero falta el segundo factor: no hay sesión todavía.
 * `mfa_setup_required` = primer ingreso (hay que configurar la aplicación de autenticación).
 */
export interface MfaChallenge {
  status: 'mfa_required' | 'mfa_setup_required'
  mfa_token: string
  expires_in: number
}

export interface MfaSetup {
  /** Clave en base32 para cargar a mano. */
  secret: string
  /** URI `otpauth://` que codifica el QR. */
  otpauth_uri: string
}

export type LoginResult = TokenResponse | MfaChallenge

export function isMfaChallenge(result: LoginResult): result is MfaChallenge {
  return result.status === 'mfa_required' || result.status === 'mfa_setup_required'
}

export interface LoginPayload {
  login: string
  password: string
}
