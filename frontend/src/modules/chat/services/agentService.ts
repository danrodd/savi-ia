import { HttpClient } from '@/lib/HttpClient'
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
      let detail = ''
      try {
        const data = (await res.json()) as { detail?: string; message?: string }
        detail = data.detail ?? data.message ?? ''
      } catch {
        // body no JSON
      }
      throw new Error(detail || `chat error: ${res.status} ${res.statusText}`)
    }
    if (!res.body) {
      throw new Error('chat error: respuesta sin cuerpo')
    }

    yield* readSseJson<ChatEvent>(res.body)
  }
}

export const agentService = new AgentService()
