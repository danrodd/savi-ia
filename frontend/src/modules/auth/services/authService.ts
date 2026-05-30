/**
 * Servicio de auth con fetch directo — NO usa HttpClient.
 *
 * Razón: el HttpClient inyecta el Bearer y maneja 401 con refresh
 * automático llamando a este mismo servicio. Si auth usara HttpClient
 * tendríamos un ciclo (HttpClient → authStore → authService → HttpClient).
 * Acá cada request es explícita: login no necesita token, refresh y
 * logout llevan el refresh en el body, /me lleva el access en el header
 * que recibe como parámetro.
 */
import { ENV } from '@/lib/env'
import type { AuthUser, LoginPayload, TokenResponse } from '../types'

async function asJsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* body no JSON */
    }
    throw new AuthRequestError(detail, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export class AuthRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
    this.name = 'AuthRequestError'
  }
}

class AuthService {
  private url(path: string): string {
    return `${ENV.API_BASE_URL.replace(/\/+$/, '')}${path}`
  }

  async login(payload: LoginPayload): Promise<TokenResponse> {
    const res = await fetch(this.url('/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return asJsonOrThrow<TokenResponse>(res)
  }

  async refresh(refreshToken: string): Promise<TokenResponse> {
    const res = await fetch(this.url('/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    return asJsonOrThrow<TokenResponse>(res)
  }

  async logout(refreshToken: string): Promise<void> {
    // Tolerante a fallos: el backend es idempotente y el frontend igual
    // limpia la sesión local. Si el endpoint falla (offline, 5xx), no
    // bloqueamos al usuario.
    try {
      await fetch(this.url('/auth/logout'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
    } catch {
      /* swallow */
    }
  }

  async me(accessToken: string): Promise<AuthUser> {
    const res = await fetch(this.url('/auth/me'), {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    return asJsonOrThrow<AuthUser>(res)
  }
}

export const authService = new AuthService()
