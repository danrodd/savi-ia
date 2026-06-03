import { HttpClient } from '@/lib/HttpClient'
import type {
  ConversationUsage,
  SystemUsageReport,
  UsageKpis,
  UsageQuery,
  UserUsageReport,
} from '../types'

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

  /** KPIs para definir tarifa (percentiles, proyección). Solo admins. */
  kpis(params: UsageQuery = {}): Promise<UsageKpis> {
    return this.http.get<UsageKpis>('/kpis', { query: { ...params } })
  }

  /** Detalle por conversación (las más caras primero). Solo admins. */
  conversations(params: UsageQuery & { limit?: number } = {}): Promise<ConversationUsage[]> {
    return this.http.get<ConversationUsage[]>('/conversations', {
      query: { ...params },
    })
  }
}

export const usageService = new UsageService()
