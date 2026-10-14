/**
 * Datos de la vista simple de "Mi consumo" (usuarios sin rol de admin):
 * cantidad de consultas y su evolución por día.
 */
import type { DailyUsage } from '../types'
import type { RangePreset } from './dateRange'

const PERIOD_LABELS: Record<string, string> = {
  today: 'Hoy',
  yesterday: 'Ayer',
  '7': 'En los últimos 7 días',
  '30': 'En los últimos 30 días',
  '90': 'En los últimos 90 días',
  custom: 'En el período elegido',
}

export function periodDescription(preset: RangePreset): string {
  return PERIOD_LABELS[String(preset)] ?? 'En el período elegido'
}

export interface QueryBar {
  day: string
  count: number
  /** Altura relativa al día con más consultas (0-100). */
  percent: number
}

/** Una barra por día, escaladas contra el día más movido. */
export function dailyQueryBars(daily: readonly DailyUsage[]): QueryBar[] {
  const sorted = [...daily].sort((a, b) => a.day.localeCompare(b.day))
  const max = Math.max(0, ...sorted.map((d) => d.totals.message_count))
  return sorted.map((d) => ({
    day: d.day,
    count: d.totals.message_count,
    percent: max === 0 ? 0 : Math.round((d.totals.message_count / max) * 100),
  }))
}
