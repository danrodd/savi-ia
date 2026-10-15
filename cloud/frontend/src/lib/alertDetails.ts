import { durationLabel, formatDay, formatInt, formatPercent, formatUsd } from '@/lib/format'
import type { Alert } from '@/lib/types'

/**
 * Detalle legible de una alerta según su regla. Las claves y unidades son las que arma
 * `cloud/backend/app/modules/alerts/rules.py`; si una regla nueva o un valor inesperado no
 * encaja, se cae a `clave: valor` para no esconder información.
 */

type Details = Record<string, unknown>
type Formatter = (details: Details) => string[] | null

const WARNINGS: Record<string, string> = {
  cert_expired: 'Certificado vencido',
  no_llm_provider: 'Sin proveedor de IA',
  local_session_in_server: 'Sesión local en un servidor',
  llm_unusable: 'Proveedor de IA inutilizable',
  credentials_unreadable: 'Credenciales ilegibles',
}

const isNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
const isText = (value: unknown): value is string => typeof value === 'string' && value !== ''

function plural(n: number, one: string, many: string): string {
  return `${formatInt(n)} ${Math.abs(n) === 1 ? one : many}`
}

function instance(d: Details): string[] {
  return isText(d.instance) ? [`Instancia ${d.instance}`] : []
}

const FORMATTERS: Record<string, Formatter> = {
  instance_offline: (d) =>
    isNumber(d.silent_minutes)
      ? [...instance(d), `Sin contacto hace ${durationLabel(d.silent_minutes * 60)}`]
      : null,

  instance_fingerprint_mismatch: (d) => (isText(d.instance) ? instance(d) : null),

  sync_stalled: (d) => {
    const streams = d.streams
    if (typeof streams !== 'object' || streams === null || Array.isArray(streams)) return null
    const stalled = Object.entries(streams as Record<string, unknown>)
      .filter((entry): entry is [string, number] => isNumber(entry[1]))
      .map(([name, hours]) => `${name} (${plural(hours, 'hora', 'horas')} sin avanzar)`)
    return stalled.length ? [...instance(d), `Envíos detenidos: ${stalled.join(', ')}`] : null
  },

  contract_rejected: (d) => (isText(d.instance) ? instance(d) : null),

  clock_skew: (d) => {
    if (!isNumber(d.skew_seconds)) return null
    const seconds = d.skew_seconds
    const direction = seconds >= 0 ? 'adelantado' : 'atrasado'
    return [...instance(d), `Reloj ${direction} ${durationLabel(Math.abs(seconds))}`]
  },

  error_rate_spike: (d) =>
    isNumber(d.turns) && isNumber(d.errors) && isNumber(d.rate)
      ? [
          `${plural(d.errors, 'turno con error', 'turnos con error')} de ${formatInt(d.turns)}`,
          `Tasa de error ${formatPercent(d.rate)}`,
        ]
      : null,

  cost_spike: (d) =>
    typeof d.cost_usd === 'string' && typeof d.median_14d_usd === 'string'
      ? [
          `Costo de hoy ${formatUsd(d.cost_usd)}`,
          `Mediana de los 14 días previos ${formatUsd(d.median_14d_usd)}`,
        ]
      : null,

  instance_warning: (d) => {
    if (!Array.isArray(d.warnings)) return null
    const labels = d.warnings.filter(isText).map((code) => WARNINGS[code] ?? code)
    return labels.length ? [...instance(d), labels.join(', ')] : null
  },

  instance_outdated: (d) =>
    isText(d.version) && isText(d.latest)
      ? [...instance(d), `Versión ${d.version}`, `Última publicada ${d.latest}`]
      : null,

  subscription_due: (d) => {
    if (!isText(d.valid_until) || !isNumber(d.days_left)) return null
    const until = formatDay(d.valid_until)
    const left = d.days_left
    if (left < 0) return [`Venció el ${until}`, `hace ${plural(-left, 'día', 'días')}`]
    return [`Vence el ${until}`, left === 0 ? 'hoy' : `quedan ${plural(left, 'día', 'días')}`]
  },

  no_usage: (d) =>
    isNumber(d.days) ? [`Sin turnos en los últimos ${plural(d.days, 'día', 'días')}`] : null,
}

function raw(value: unknown): string {
  return typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value)
}

/** Fragmentos del detalle de una alerta, listos para unir con « · ». */
export function alertDetailParts(alert: Pick<Alert, 'rule_code' | 'details'>): string[] {
  const details = alert.details ?? {}
  if (!Object.keys(details).length) return []
  try {
    const parts = FORMATTERS[alert.rule_code]?.(details)
    if (parts?.length) return parts
  } catch {
    // Un valor inesperado no puede romper la lista de alertas: se usa el formato genérico.
  }
  return Object.entries(details).map(([key, value]) => `${key}: ${raw(value)}`)
}

export function alertDetail(alert: Pick<Alert, 'rule_code' | 'details'>): string {
  return alertDetailParts(alert).join(' · ')
}
