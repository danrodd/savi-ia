/** Formateo de cifras y fechas de la consola (es-CO, zona America/Bogota). */

const ZONE = 'America/Bogota'

export type Tone = 'ok' | 'warn' | 'bad' | 'muted'

export function formatInt(value: number): string {
  return new Intl.NumberFormat('es-CO').format(value)
}

export function formatUsd(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(number)) return '—'
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: number !== 0 && Math.abs(number) < 1 ? 4 : 2,
  }).format(number)
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('es-CO', { style: 'percent', maximumFractionDigits: 1 }).format(
    value,
  )
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value < 1000) return `${value} ms`
  const seconds = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 }).format(value / 1000)
  return `${seconds} s`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: ZONE,
  }).format(new Date(value))
}

export function formatDay(value: string): string {
  // `YYYY-MM-DD` ya es el día en Bogotá: se arma sin pasar por zonas horarias.
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}

/** «hace 3 min», «hace 2 h», «hace 4 días». */
export function relativeTime(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return 'nunca'
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(value).getTime()) / 1000))
  return `hace ${durationLabel(seconds)}`
}

export function durationLabel(seconds: number): string {
  if (seconds < 60) return 'menos de un minuto'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours} h`
  return `${Math.round(hours / 24)} días`
}

/** Frescura de los datos (§7.3): ámbar pasada 1 h, rojo pasadas 24 h. */
export function freshnessTone(seconds: number | null): Tone {
  if (seconds === null) return 'muted'
  if (seconds >= 24 * 3600) return 'bad'
  if (seconds >= 3600) return 'warn'
  return 'ok'
}

export function freshnessLabel(seconds: number | null): string {
  if (seconds === null) return 'Sin datos todavía'
  return `Datos hasta hace ${durationLabel(seconds)}`
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  soporte: 'Soporte',
  comercial: 'Comercial',
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role
}

const INSTANCE_STATUS: Record<string, string> = {
  active: 'Activa',
  suspended: 'Suspendida',
  revoked: 'Revocada',
}

export function instanceStatusLabel(status: string): string {
  return INSTANCE_STATUS[status] ?? status
}

const REASONS: Record<string, string> = {
  manual: 'Suspendida a mano',
  fingerprint_mismatch: 'La huella cambió (posible copia)',
  client_suspended: 'Cliente suspendido',
}

export function reasonLabel(reason: string | null): string {
  return reason ? (REASONS[reason] ?? reason) : '—'
}
