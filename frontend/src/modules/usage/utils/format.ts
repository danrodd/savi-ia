/**
 * Formateadores de la vista de consumo.
 *
 * El dato fuente es USD; `formatCop` aplica la tasa que el backend expone
 * (`usd_to_cop_rate`) para mostrar pesos. Es solo presentación — no se
 * hace aritmética de dinero acá más allá de la multiplicación de display.
 */

const COP = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
})

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

const NUM = new Intl.NumberFormat('es-CO')

export function formatCop(usd: number, rate: number): string {
  return COP.format(usd * rate)
}

export function formatUsd(usd: number): string {
  return USD.format(usd)
}

export function formatTokens(n: number): string {
  return NUM.format(n)
}

/** `YYYY-MM-DD` → `02 jun`. Se parsea como fecha local para no correr el día. */
export function formatDay(iso: string): string {
  const parts = iso.split('-')
  const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
  return date.toLocaleDateString('es-CO', { day: '2-digit', month: 'short' })
}
