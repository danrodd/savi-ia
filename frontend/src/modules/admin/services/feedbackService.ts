import { HttpClient } from '@/lib/HttpClient'
import type { FeedbackPage, FeedbackSummary } from '../types'

type Query = Record<string, string | number>

class FeedbackAdminService {
  private readonly http = new HttpClient('/admin/feedback')

  list(query: Query): Promise<FeedbackPage> {
    return this.http.get<FeedbackPage>('', { query })
  }

  summary(query: Query): Promise<FeedbackSummary> {
    return this.http.get<FeedbackSummary>('/summary', { query })
  }

  /** CSV (UTF-8 con BOM, separador `;`) con los mismos filtros. */
  exportCsv(query: Query): Promise<Blob> {
    return this.http.getBlob('/export.csv', { query })
  }
}

export const feedbackAdminService = new FeedbackAdminService()
