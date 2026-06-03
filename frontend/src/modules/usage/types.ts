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

export interface UserUsageReport {
  user_id: number
  period_start: string
  period_end: string
  totals: UsageTotals
  daily: DailyUsage[]
  usd_to_cop_rate: number
}

export interface SystemUsageReport {
  period_start: string
  period_end: string
  totals: UsageTotals
  per_user: UserUsage[]
  daily: DailyUsage[]
  usd_to_cop_rate: number
}

export interface UsageQuery {
  start?: string
  end?: string
}
