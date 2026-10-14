import type { FeedbackFilters, FeedbackItem, FeedbackRating, FeedbackReason } from '../types'

export const FEEDBACK_REASON_LABELS: Record<FeedbackReason, string> = {
  dato_incorrecto: 'El dato es incorrecto',
  no_entendio: 'No entendió la pregunta',
  incompleta: 'Está incompleta',
  muy_lenta: 'Tardó demasiado',
  otra: 'Otra cosa',
}

export const FEEDBACK_RATING_LABELS: Record<FeedbackRating, string> = {
  up: 'Me sirvió',
  down: 'No me sirvió',
}

export const FEEDBACK_PAGE_SIZE = 25

export function emptyFeedbackFilters(): FeedbackFilters {
  return { rating: '', reason: '', from: '', to: '', model: '', user: '', text: '' }
}

/**
 * Parámetros de consulta del backend a partir de los filtros de la pantalla.
 * Omite los vacíos; `text` viaja como `q` y las fechas como `from`/`to`.
 */
export function buildFeedbackQuery(
  filters: FeedbackFilters,
  page?: { limit: number; offset: number },
): Record<string, string | number> {
  const query: Record<string, string | number> = {}
  const set = (key: string, value: string): void => {
    const clean = value.trim()
    if (clean) query[key] = clean
  }
  set('rating', filters.rating)
  // El motivo solo existe con 👎: no se manda uno contradictorio.
  if (filters.rating !== 'up') set('reason', filters.reason)
  set('from', filters.from)
  set('to', filters.to)
  set('model', filters.model)
  set('user', filters.user)
  set('q', filters.text)
  if (page) {
    query.limit = page.limit
    query.offset = page.offset
  }
  return query
}

/** Alto relativo (0–100) de una barra del gráfico diario. */
export function barPercent(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 0
  return Math.max(4, Math.round((value / max) * 100))
}

export function shortQuestion(text: string | null, max = 90): string {
  const clean = (text ?? '').replace(/\s+/g, ' ').trim()
  if (!clean) return '—'
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}

/** Motivo principal del resumen, listo para mostrar. */
export function topReasonLabel(reasons: { reason: FeedbackReason; count: number }[]): string {
  const top = reasons[0]
  return top ? `${FEEDBACK_REASON_LABELS[top.reason]} (${top.count})` : '—'
}

export const FEEDBACK_EXPORT_HEADERS = [
  'Fecha',
  'Usuario',
  'Nombre',
  'Calificación',
  'Motivo',
  'Comentario',
  'Pregunta',
  'Respuesta',
  'Proveedor',
  'Modelo',
  'Costo USD',
  'Herramientas',
  'Base',
  'Conversación',
  'Mensaje',
]

/** Filas para el Excel: mismas columnas que el CSV del backend. */
export function feedbackExportRows(items: FeedbackItem[]): (string | number)[][] {
  return [
    FEEDBACK_EXPORT_HEADERS,
    ...items.map((i) => [
      i.created_at,
      i.user_login ?? '',
      i.user_name ?? '',
      FEEDBACK_RATING_LABELS[i.rating],
      i.reason ? FEEDBACK_REASON_LABELS[i.reason] : '',
      i.comment ?? '',
      i.question ?? '',
      i.answer,
      i.provider ?? '',
      i.model ?? '',
      i.cost_usd ?? '',
      i.tools.join(', '),
      i.database_code ?? '',
      i.conversation_id,
      i.message_id,
    ]),
  ]
}
