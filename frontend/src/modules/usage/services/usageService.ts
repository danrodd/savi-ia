import { HttpClient } from '@/lib/HttpClient'
import type { SystemUsageReport, UsageQuery, UserUsageReport } from '../types'

class UsageService {
  private readonly http = new HttpClient('/usage')

  /** Consumo del usuario autenticado. */
  me(params: UsageQuery = {}): Promise<UserUsageReport> {
    return this.http.get<UserUsageReport>('/me', { query: { ...params } })
  }

  /** Consumo global del sistema. Solo admins (el backend devuelve 403 si no). */
  system(params: UsageQuery = {}): Promise<SystemUsageReport> {
    return this.http.get<SystemUsageReport>('/system', { query: { ...params } })
  }
}

export const usageService = new UsageService()
