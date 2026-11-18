import { HttpClient } from '@/lib/HttpClient'

/** Un turno del chat que terminó en error, como lo devuelve `/admin/failed-turns`. */
export interface FailedTurn {
  message_id: string
  conversation_id: string
  conversation_title: string | null
  user_id: number | null
  created_at: string
  error_code: string | null
  error_message: string | null
  support_code: string | null
  provider: string | null
  model: string | null
  erp_queries: number
}

class FailedTurnsService {
  private readonly http = new HttpClient('/admin/failed-turns')

  list(limit = 50): Promise<FailedTurn[]> {
    return this.http.get<FailedTurn[]>('', { query: { limit } })
  }
}

export const failedTurnsService = new FailedTurnsService()
