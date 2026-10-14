import type { FeedbackInput, FeedbackRating, FeedbackReason, MessageFeedback } from '../types'

export const FEEDBACK_REASONS: { value: FeedbackReason; label: string }[] = [
  { value: 'dato_incorrecto', label: 'El dato es incorrecto' },
  { value: 'no_entendio', label: 'No entendió mi pregunta' },
  { value: 'incompleta', label: 'Está incompleta' },
  { value: 'muy_lenta', label: 'Tardó demasiado' },
  { value: 'otra', label: 'Otra cosa' },
]

export const FEEDBACK_COMMENT_MAX = 1000

export type FeedbackClickOutcome =
  /** Guardar directo (👍, o 👎 ya sin pasos). */
  | { kind: 'save'; input: FeedbackInput }
  /** Quitar la calificación activa. */
  | { kind: 'clear' }
  /** Pedir el motivo antes de guardar el 👎. */
  | { kind: 'ask-reason' }

/**
 * Qué pasa al tocar 👍 o 👎 según lo que ya hay:
 * - tocar la calificación activa la quita;
 * - 👍 guarda en el acto;
 * - 👎 abre el diálogo del motivo.
 */
export function resolveFeedbackClick(
  current: MessageFeedback | null | undefined,
  clicked: FeedbackRating,
): FeedbackClickOutcome {
  if (current?.rating === clicked) return { kind: 'clear' }
  if (clicked === 'up') return { kind: 'save', input: { rating: 'up' } }
  return { kind: 'ask-reason' }
}
