import { HttpClient, HttpRequestError } from '@/lib/HttpClient'
import { readSseJson } from '@/lib/streamSse'
import type { ChatEvent, SendChatBody } from '../types'

/**
 * Turnos del chat.
 *
 * El turno vive en el servidor y no en esta conexión: cortar el stream ya no
 * detiene la generación. Por eso hay tres operaciones además de `stream`:
 * preguntar si quedó algo en curso, reengancharse a ello y detenerlo de
 * verdad. Ver `docs/chat-turnos-en-segundo-plano.md`.
 */
class AgentService {
  private readonly http = new HttpClient()

  async *stream(body: SendChatBody, signal: AbortSignal): AsyncGenerator<ChatEvent, void, void> {
    const res = await this.http.raw('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    yield* this.readStream(res)
  }

  /** ¿Quedó una respuesta generándose en esta conversación? */
  async isActive(conversationId: string): Promise<boolean> {
    const res = await this.http.get<{ activo: boolean }>('/chat/activo', {
      query: { conversation_id: conversationId },
    })
    return res.activo
  }

  /**
   * Reengancha a un turno en curso. El servidor reenvía desde el evento 0, así
   * que el mensaje se reconstruye entero sin necesidad de un cursor.
   */
  async *attach(
    conversationId: string,
    signal: AbortSignal,
  ): AsyncGenerator<ChatEvent, void, void> {
    const res = await this.http.raw('/chat/stream', {
      method: 'GET',
      query: { conversation_id: conversationId },
      signal,
    })
    yield* this.readStream(res)
  }

  /** Detiene el turno. Abortar el fetch ya no alcanza. */
  async stop(conversationId: string): Promise<void> {
    await this.http.post<void>('/chat/detener', undefined, {
      query: { conversation_id: conversationId },
    })
  }

  private async *readStream(res: Response): AsyncGenerator<ChatEvent, void, void> {
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
