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
  access_token: string
  refresh_token: string
  token_type: 'Bearer'
  expires_in: number
  user: AuthUser
}

export interface LoginPayload {
  login: string
  password: string
}
