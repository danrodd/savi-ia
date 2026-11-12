import type { ResultColumnKind } from '../services/resultSetService'

const numberFormat = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 })

/** "Mostrando 8 de 214 filas", "214 filas" o "Mostrando 30 de más de 10.000 filas". */
export function rowCountLabel(shown: number, total: number, lowerBound: boolean): string {
  const totalText = `${lowerBound ? 'más de ' : ''}${numberFormat.format(total)}`
  if (shown >= total && !lowerBound) return `${totalText} ${total === 1 ? 'fila' : 'filas'}`
  return `Mostrando ${numberFormat.format(shown)} de ${totalText} filas`
}

export function formatPreviewCell(value: unknown, kind: ResultColumnKind): string {
  if (value === null || value === undefined) return '—'
  if (kind === 'number' && typeof value === 'number') return numberFormat.format(value)
  if (kind === 'date' && typeof value === 'string') {
    const [year, month, day] = value.slice(0, 10).split('-')
    return year && month && day ? `${day}/${month}/${year}` : value
  }
  return String(value)
}
