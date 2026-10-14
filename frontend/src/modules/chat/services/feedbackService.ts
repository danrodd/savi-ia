import { HttpClient } from '@/lib/HttpClient'
import type { MessageFeedback } from '../types'

class FeedbackService {
  private readonly http = new HttpClient('/conversations')

  /** Califica o reemplaza la calificación. Devuelve lo guardado. */
  set(
    conversationId: string,
    messageId: string,
    feedback: MessageFeedback,
  ): Promise<MessageFeedback> {
    return this.http.put<MessageFeedback>(
      `/${conversationId}/messages/${messageId}/feedback`,
      feedback,
    )
  }

  /** Quita la calificación (idempotente). */
  clear(conversationId: string, messageId: string): Promise<void> {
    return this.http.delete<void>(`/${conversationId}/messages/${messageId}/feedback`)
  }
}

export const feedbackService = new FeedbackService()
