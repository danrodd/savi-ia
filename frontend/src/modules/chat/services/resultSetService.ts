import { HttpClient } from '@/lib/HttpClient'

export type ResultColumnKind = 'text' | 'number' | 'date'
export type ExportFormat = 'xlsx' | 'pdf' | 'csv'

export interface ResultSetPreview {
  id: string
  title: string
  columns: { key: string; label: string; kind: ResultColumnKind }[]
  rows: unknown[][]
  total_rows: number
  total_is_lower_bound: boolean
  created_at: string
}

class ResultSetService {
  private readonly http = new HttpClient('/result-sets')

  preview(id: string): Promise<ResultSetPreview> {
    return this.http.get<ResultSetPreview>(`/${id}`)
  }

  /** El archivo completo lo genera el servidor con todas las filas de la consulta. */
  export(id: string, format: ExportFormat): Promise<Blob> {
    return this.http.getBlob(`/${id}/export`, { query: { format } })
  }
}

export const resultSetService = new ResultSetService()
