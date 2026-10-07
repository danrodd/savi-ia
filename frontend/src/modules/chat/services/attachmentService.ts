import { HttpClient } from '@/lib/HttpClient'
import type { ChatAttachment } from '../types'

/** Imágenes adjuntas del chat: se suben aparte y el mensaje las referencia por id. */
class AttachmentService {
  private readonly http = new HttpClient()

  upload(file: File, signal?: AbortSignal): Promise<ChatAttachment> {
    const form = new FormData()
    form.append('file', file)
    return this.http.postForm<ChatAttachment>('/chat/attachments', form, { signal })
  }

  /** `<img src>` no manda el bearer: los bytes se piden con el cliente HTTP. */
  download(id: string, signal?: AbortSignal): Promise<Blob> {
    return this.http.getBlob(`/chat/attachments/${encodeURIComponent(id)}`, { signal })
  }
}

export const attachmentService = new AttachmentService()
