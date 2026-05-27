import { HttpClient } from '@/lib/HttpClient'
import { readSseJson } from '@/lib/streamSse'
import type { ChatEvent } from '../types'

class AgentService {
  private readonly http = new HttpClient()

  async *stream(
    conversationId: string,
    message: string,
    signal: AbortSignal,
  ): AsyncGenerator<ChatEvent, void, void> {
    const res = await this.http.raw('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, message }),
      signal,
    })

    if (!res.ok || !res.body) {
      throw new Error(`chat error: ${res.status} ${res.statusText}`)
    }

    yield* readSseJson<ChatEvent>(res.body)
  }
}

export const agentService = new AgentService()
