/**
 * Lista de conversaciones de la barra lateral: búsqueda, agrupación por
 * antigüedad y ocultamiento de las que nunca se usaron.
 */
import { calendarDaysBetween, isSameMonth } from '@/lib/dateTime'
import type { Conversation } from '../types'

export type ConversationGroupKey = 'today' | 'yesterday' | 'week' | 'month' | 'older'

export interface ConversationGroup {
  key: ConversationGroupKey
  label: string
  items: Conversation[]
}

const GROUP_LABELS: Record<ConversationGroupKey, string> = {
  today: 'Hoy',
  yesterday: 'Ayer',
  week: 'Últimos 7 días',
  month: 'Este mes',
  older: 'Anteriores',
}

const GROUP_ORDER: ConversationGroupKey[] = ['today', 'yesterday', 'week', 'month', 'older']

/** Título que el backend le pone a una conversación hasta que se nombra. */
export const DEFAULT_CONVERSATION_TITLE = 'Nueva conversación'

/** Minúsculas y sin tildes: "Facturación" coincide con "facturacion". */
export function normalizeSearch(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .trim()
}

export function filterConversations(
  conversations: readonly Conversation[],
  query: string,
): Conversation[] {
  const words = normalizeSearch(query).split(/\s+/).filter(Boolean)
  if (words.length === 0) return [...conversations]
  return conversations.filter((c) => {
    const title = normalizeSearch(c.title)
    return words.every((w) => title.includes(w))
  })
}

/**
 * Conversación creada pero nunca usada: el backend informa que no tiene
 * mensajes activos (`message_count === 0`). Se oculta de la lista para que no
 * se acumulen entradas "Nueva conversación" vacías.
 *
 * Solo el conteo decide: el título o las fechas no son confiables (una
 * conversación real puede conservar el título por defecto si el autotítulo
 * falló). Si el backend no manda el dato, no se oculta nada.
 */
export function isUntouchedConversation(c: Conversation): boolean {
  return c.message_count === 0
}

/** Oculta las sin uso, salvo la que está abierta en este momento. */
export function visibleConversations(
  conversations: readonly Conversation[],
  activeId: string | null,
): Conversation[] {
  return conversations.filter((c) => c.id === activeId || !isUntouchedConversation(c))
}

export function groupKeyFor(updatedAt: string, now: Date): ConversationGroupKey {
  const date = new Date(updatedAt)
  if (Number.isNaN(date.getTime())) return 'older'
  const days = calendarDaysBetween(date, now)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days <= 7) return 'week'
  if (isSameMonth(date, now)) return 'month'
  return 'older'
}

/** Agrupa conservando el orden recibido y descarta los grupos vacíos. */
export function groupConversations(
  conversations: readonly Conversation[],
  now: Date = new Date(),
): ConversationGroup[] {
  const buckets = new Map<ConversationGroupKey, Conversation[]>()
  for (const c of conversations) {
    const key = groupKeyFor(c.updated_at, now)
    const list = buckets.get(key)
    if (list) list.push(c)
    else buckets.set(key, [c])
  }
  return GROUP_ORDER.flatMap((key) => {
    const items = buckets.get(key)
    return items ? [{ key, label: GROUP_LABELS[key], items }] : []
  })
}
