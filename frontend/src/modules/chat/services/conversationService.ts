import { HttpClient } from '@/lib/HttpClient'
import type { Conversation, ConversationDetail } from '../types'

class ConversationService {
  private readonly http = new HttpClient('/conversations')

  list(
    params: { user_id?: string; limit?: number; offset?: number } = {},
  ): Promise<Conversation[]> {
    return this.http.get<Conversation[]>('', { query: params })
  }

  /** Sin `erpDatabaseId` el backend usa la base con la que inició sesión el usuario. */
  create(options: { title?: string; erpDatabaseId?: string | null } = {}): Promise<Conversation> {
    return this.http.post<Conversation>('', {
      title: options.title ?? null,
      user_id: null,
      erp_database_id: options.erpDatabaseId ?? null,
    })
  }

  get(id: string): Promise<ConversationDetail> {
    return this.http.get<ConversationDetail>(`/${id}`)
  }

  getWithVersions(id: string): Promise<ConversationDetail> {
    return this.http.get<ConversationDetail>(`/${id}`, {
      query: { include_superseded: true },
    })
  }

  rename(id: string, title: string): Promise<Conversation> {
    return this.http.patch<Conversation>(`/${id}`, { title })
  }

  delete(id: string): Promise<void> {
    return this.http.delete<void>(`/${id}`)
  }
}

export const conversationService = new ConversationService()
