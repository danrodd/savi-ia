/**
 * Fechas legibles para personas: "Hoy 14:32", "Ayer 09:10", "6 oct 14:32".
 *
 * Todo se calcula en la zona horaria de la app (Bogotá) para que dos personas
 * que ven el mismo mensaje lean la misma hora. Se arma a mano con
 * `formatToParts` en lugar de depender del formato de cada navegador.
 */

export const APP_TIME_ZONE = 'America/Bogota'

const MONTHS_SHORT = [
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
] as const

interface ZonedParts {
  year: number
  month: number
  day: number
  hour: number
  minute: number
}

const partsFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: APP_TIME_ZONE,
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: 'numeric',
  minute: 'numeric',
  hourCycle: 'h23',
})

function zonedParts(date: Date): ZonedParts {
  const out: Record<string, number> = {}
  for (const part of partsFormatter.formatToParts(date)) {
    if (part.type !== 'literal') out[part.type] = Number(part.value)
  }
  return {
    year: out.year ?? 0,
    month: out.month ?? 1,
    day: out.day ?? 1,
    // Algunos motores devuelven 24 a medianoche con h23 en modo parts.
    hour: (out.hour ?? 0) % 24,
    minute: out.minute ?? 0,
  }
}

/** Días de calendario entre dos fechas, medidos en la zona de la app. */
export function calendarDaysBetween(from: Date, to: Date): number {
  const a = zonedParts(from)
  const b = zonedParts(to)
  const dayA = Date.UTC(a.year, a.month - 1, a.day)
  const dayB = Date.UTC(b.year, b.month - 1, b.day)
  return Math.round((dayB - dayA) / 86_400_000)
}

export function isSameMonth(a: Date, b: Date): boolean {
  const pa = zonedParts(a)
  const pb = zonedParts(b)
  return pa.year === pb.year && pa.month === pb.month
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

function clock(p: ZonedParts): string {
  return `${pad(p.hour)}:${pad(p.minute)}`
}

/**
 * "Ahora" (menos de un minuto), "Hoy 14:32", "Ayer 09:10", "6 oct 14:32".
 * Si es de otro año se agrega el año: "6 oct 2025 14:32".
 */
export function formatMessageTime(iso: string | Date, now: Date = new Date()): string {
  const date = iso instanceof Date ? iso : new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  if (Math.abs(now.getTime() - date.getTime()) < 60_000) return 'Ahora'

  const p = zonedParts(date)
  const days = calendarDaysBetween(date, now)
  if (days === 0) return `Hoy ${clock(p)}`
  if (days === 1) return `Ayer ${clock(p)}`

  const month = MONTHS_SHORT[p.month - 1] ?? ''
  const sameYear = zonedParts(now).year === p.year
  return sameYear ? `${p.day} ${month} ${clock(p)}` : `${p.day} ${month} ${p.year} ${clock(p)}`
}

/** Fecha y hora completas para el tooltip: "6 de octubre de 2026, 14:32". */
export function formatFullDateTime(iso: string | Date): string {
  const date = iso instanceof Date ? iso : new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('es-CO', {
    timeZone: APP_TIME_ZONE,
    dateStyle: 'long',
    timeStyle: 'short',
    hourCycle: 'h23',
  })
}
