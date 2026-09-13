import { HttpClient, HttpRequestError } from '@/lib/HttpClient'
import { readSseJson } from '@/lib/streamSse'
import type { ChatEvent, SendChatBody } from '../types'

class AgentService {
  private readonly http = new HttpClient()

  async *stream(body: SendChatBody, signal: AbortSignal): AsyncGenerator<ChatEvent, void, void> {
    const res = await this.http.raw('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })

    if (!res.ok) {
      let data: { detail?: string; message?: string; errorCode?: string } = {}
      try {
        data = await res.json()
      } catch {
        // body no JSON
      }
      const detail = typeof data.detail === 'string' ? data.detail : (data.message ?? '')
      // HttpRequestError conserva `errorCode` para que el store detecte
      // `erp_database_unavailable` (409 antes de abrir el stream).
      throw new HttpRequestError(
        detail || `chat error: ${res.status} ${res.statusText}`,
        res.status,
        data,
      )
    }
    if (!res.body) {
      throw new Error('chat error: respuesta sin cuerpo')
    }

    yield* readSseJson<ChatEvent>(res.body)
  }
}

export const agentService = new AgentService()
