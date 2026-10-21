import { ENV } from '@/lib/env'
import { HttpClient } from '@/lib/HttpClient'
import type { UpdateStatus } from '../types'

const http = new HttpClient('/updates')

class UpdatesService {
  getStatus(): Promise<UpdateStatus> {
    return http.get<UpdateStatus>('/status')
  }

  apply(): Promise<UpdateStatus> {
    return http.post<UpdateStatus>('/apply')
  }

  /**
   * Versión que responde `/health`, o `null` si SAVI no responde.
   *
   * Sin `HttpClient` a propósito: mientras el instalador reemplaza los
   * archivos el backend está caído, y un 401 o un error de red no tienen que
   * disparar el refresh de sesión ni un aviso.
   */
  async healthVersion(): Promise<string | null> {
    try {
      const base = ENV.API_BASE_URL.replace(/\/+$/, '')
      const response = await fetch(`${base}/health`, { cache: 'no-store' })
      if (!response.ok) return null
      const body = (await response.json()) as { version?: unknown }
      return typeof body.version === 'string' ? body.version : null
    } catch {
      return null
    }
  }
}

export const updatesService = new UpdatesService()
