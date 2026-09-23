/**
 * Consumo por cliente: traduce el id de la base del ERP a algo legible.
 *
 * El backend manda solo el id; el nombre sale del listado de bases que el
 * administrador ya tiene cargado. Una base borrada o desconocida no rompe la
 * vista: se muestra un id corto para poder rastrearla.
 */
import type { DatabaseUsage } from '../types'

export interface DatabaseRef {
  id: string
  code: string
  name: string
}

export interface DatabaseRow {
  key: string
  label: string
  responses: number
  tokens: number
  costUsd: number
  /** Porcentaje del costo del período (0-100), para comparar clientes. */
  share: number
}

export function databaseLabel(id: string | null, databases: readonly DatabaseRef[]): string {
  if (id === null) return 'Sin base (legado)'
  const found = databases.find((d) => d.id === id)
  return found ? found.code : `Base ${id.slice(0, 8)}`
}

export function buildDatabaseRows(
  rows: readonly DatabaseUsage[],
  databases: readonly DatabaseRef[],
): DatabaseRow[] {
  const totalCost = rows.reduce((sum, r) => sum + r.totals.cost_usd, 0)
  return rows.map((r) => ({
    key: r.erp_database_id ?? 'legacy',
    label: databaseLabel(r.erp_database_id, databases),
    responses: r.totals.message_count,
    tokens: r.totals.total_tokens,
    costUsd: r.totals.cost_usd,
    share: totalCost > 0 ? (r.totals.cost_usd / totalCost) * 100 : 0,
  }))
}
