/**
 * Tipos del módulo de consumo. Reflejan 1:1 las responses del backend
 * (`/usage/me`, `/usage/system`). El costo viaja SIEMPRE en USD; la
 * conversión a COP la hace la vista con `usd_to_cop_rate`.
 */

export interface UsageTotals {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
  total_tokens: number
  message_count: number
  cost_usd: number
  /**
   * Turnos cuyo modelo no tenía tarifa cargada: su costo NO está en
   * `cost_usd`. Si es > 0, el total mostrado es menor al real.
   */
  untariffed_count: number
}

export interface DailyUsage {
  /** Fecha local (zona de reporte del backend), formato `YYYY-MM-DD`. */
  day: string
  totals: UsageTotals
}

export interface UserUsage {
  /** `null` = conversaciones legadas anteriores a auth. */
  user_id: number | null
  totals: UsageTotals
}

/** Consumo agregado de un (proveedor, modelo). Siempre viene con modelo:
 * el desglose "por proveedor" se arma sumando las filas que comparten
 * `provider` en el cliente. */
export interface ProviderUsage {
  provider: string | null
  model: string | null
  totals: UsageTotals
}

export interface DailyProviderUsage {
  day: string
  provider: string | null
  totals: UsageTotals
}

export interface UserUsageReport {
  user_id: number
  period_start: string
  period_end: string
  totals: UsageTotals
  daily: DailyUsage[]
  per_provider: ProviderUsage[]
  daily_by_provider: DailyProviderUsage[]
  usd_to_cop_rate: number
}

export interface SystemUsageReport {
  period_start: string
  period_end: string
  totals: UsageTotals
  per_user: UserUsage[]
  daily: DailyUsage[]
  per_provider: ProviderUsage[]
  daily_by_provider: DailyProviderUsage[]
  usd_to_cop_rate: number
}

export type UsageProviderKind = 'claude' | 'gemini' | 'openai'

export interface UsageQuery {
  start?: string
  end?: string
  /** Fecha sola (AAAA-MM-DD), interpretada en la zona de reporte del backend. */
  from?: string
  to?: string
  provider?: UsageProviderKind[]
  model?: string[]
}

export interface ConversationStats {
  count: number
  avg_cost_usd: number
  p50_cost_usd: number
  p90_cost_usd: number
  p95_cost_usd: number
  max_cost_usd: number
  avg_tokens: number
  avg_turns: number
}

export interface UserStats {
  active_count: number
  avg_cost_usd: number
  avg_conversations: number
}

export interface UsageKpis {
  period_start: string
  period_end: string
  period_days: number
  total_cost_usd: number
  total_tokens: number
  turns_count: number
  avg_cost_per_turn_usd: number
  avg_tokens_per_turn: number
  conversations: ConversationStats
  users: UserStats
  avg_cost_per_day_usd: number
  projected_monthly_cost_usd: number
  cache_read_ratio: number
  usd_to_cop_rate: number
}

export interface ConversationUsage {
  conversation_id: string
  user_id: number | null
  title: string
  turns: number
  total_tokens: number
  cost_usd: number
  last_activity: string
}
