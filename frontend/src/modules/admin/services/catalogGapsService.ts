import { HttpClient } from '@/lib/HttpClient'

export type GapKind = 'free_query' | 'failed_query' | 'query_limit'

/** Una pregunta que el catálogo de datos no cubrió, como la agrupa `/admin/catalog-gaps`. */
export interface CatalogGap {
  question: string
  kinds: GapKind[]
  times: number
  last_at: string
  tables: string[]
  conversation_id: string
}

export interface CatalogGapReport {
  start: string
  end: string
  totals: Record<GapKind, number>
  gaps: CatalogGap[]
  top_tables: { table: string; times: number }[]
}

/** Días calendario (AAAA-MM-DD), ambos inclusivos. Sin fechas: los últimos 30 días. */
export interface CatalogGapPeriod {
  from?: string
  to?: string
}

function toQuery(period: CatalogGapPeriod): Record<string, string> {
  const query: Record<string, string> = {}
  if (period.from) query.from = period.from
  if (period.to) query.to = period.to
  return query
}

class CatalogGapsService {
  private readonly http = new HttpClient('/admin/catalog-gaps')

  report(period: CatalogGapPeriod = {}): Promise<CatalogGapReport> {
    return this.http.get<CatalogGapReport>('', { query: toQuery(period) })
  }

  /** CSV (UTF-8 con BOM, separador `;`) del mismo periodo. */
  exportCsv(period: CatalogGapPeriod = {}): Promise<Blob> {
    return this.http.getBlob('/export.csv', { query: toQuery(period) })
  }
}

export const catalogGapsService = new CatalogGapsService()

export const GAP_KIND_LABELS: Record<GapKind, string> = {
  free_query: 'Resuelta con consulta libre',
  failed_query: 'Consulta fallida',
  query_limit: 'Llegó al tope de consultas',
}
