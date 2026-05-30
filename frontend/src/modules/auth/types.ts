export interface AuthUser {
  id: number
  login: string
  full_name: string
  is_admin: boolean
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
