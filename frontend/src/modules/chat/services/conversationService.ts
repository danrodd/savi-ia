import { HttpClient } from '@/lib/HttpClient'
import type { Conversation, ConversationDetail } from '../types'

class ConversationService {
  private readonly http = new HttpClient('/conversations')

  list(
    params: { user_id?: string; limit?: number; offset?: number } = {},
  ): Promise<Conversation[]> {
    return this.http.get<Conversation[]>('', { query: params })
  }

  create(title?: string): Promise<Conversation> {
    return this.http.post<Conversation>('', { title: title ?? null, user_id: null })
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
}

export const conversationService = new ConversationService()
