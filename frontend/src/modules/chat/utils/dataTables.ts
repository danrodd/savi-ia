import type { ResultColumnKind } from '../services/resultSetService'

const numberFormat = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 })

/** "Mostrando 8 de 214 filas", "214 filas" o "Mostrando 30 de más de 10.000 filas". */
export function rowCountLabel(shown: number, total: number, lowerBound: boolean): string {
  const totalText = `${lowerBound ? 'más de ' : ''}${numberFormat.format(total)}`
  if (shown >= total && !lowerBound) return `${totalText} ${total === 1 ? 'fila' : 'filas'}`
  return `Mostrando ${numberFormat.format(shown)} de ${totalText} filas`
}

const DATE_STYLE = { DAY: 'day', MONTH: 'month', YEAR: 'year' } as const
export type DateStyle = (typeof DATE_STYLE)[keyof typeof DATE_STYLE]

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

function dateParts(value: unknown): [string, string, string] | null {
  if (typeof value !== 'string') return null
  const [year, month, day] = value.slice(0, 10).split('-')
  return year && month && day ? [year, month, day] : null
}

/**
 * Cómo mostrar cada columna de fechas, mirando la columna entera: una consulta
 * agrupada por mes o por año trae el primer día del periodo (2025-11-01), que
 * se muestra "nov 2025" o "2025" en lugar de "01/11/2025". Igual que en los PDF.
 */
export function dateStyles(
  kinds: readonly ResultColumnKind[],
  rows: readonly (readonly unknown[])[],
): DateStyle[] {
  return kinds.map((kind, index) => {
    if (kind !== 'date') return DATE_STYLE.DAY
    const parts = rows.map((row) => dateParts(row[index])).filter((p) => p !== null)
    if (!parts.length || parts.some(([, , day]) => day !== '01')) return DATE_STYLE.DAY
    const allJanuary = parts.length > 1 && parts.every(([, month]) => month === '01')
    return allJanuary ? DATE_STYLE.YEAR : DATE_STYLE.MONTH
  })
}

export function formatPreviewCell(
  value: unknown,
  kind: ResultColumnKind,
  style: DateStyle = DATE_STYLE.DAY,
): string {
  if (value === null || value === undefined) return '—'
  if (kind === 'number' && typeof value === 'number') return numberFormat.format(value)
  if (kind === 'date' && typeof value === 'string') {
    const parts = dateParts(value)
    if (!parts) return value
    const [year, month, day] = parts
    if (style === DATE_STYLE.YEAR) return year
    if (style === DATE_STYLE.MONTH) return `${MONTHS[Number(month) - 1] ?? month} ${year}`
    return `${day}/${month}/${year}`
  }
  return String(value)
}
