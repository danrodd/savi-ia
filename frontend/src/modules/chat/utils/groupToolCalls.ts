import type { ToolCall, ToolCallGroup } from '../types'
import { getToolLabel } from './toolLabels'

/**
 * Agrupa tool calls por el label público que mostraríamos al usuario,
 * preservando el orden de primera aparición. Tools distintas que comparten
 * el mismo label (p.ej. `consultar_libre` y `consultar_datos` → "Consultando
 * información del ERP") se fusionan en una sola pill con contador.
 *
 * El status agregado prioriza running > error > success — así un grupo
 * donde aún corre alguna tool se muestra activo aunque otras ya hayan
 * terminado, y un error parcial no se enmascara con un éxito posterior.
 */
export function groupToolCalls(calls: ToolCall[]): ToolCallGroup[] {
  const byLabel = new Map<string, ToolCallGroup>()
  for (const c of calls) {
    const label = getToolLabel(c.name)
    const existing = byLabel.get(label)
    if (existing) {
      existing.count++
      if (c.status === 'running') existing.status = 'running'
      else if (c.status === 'error' && existing.status !== 'running') existing.status = 'error'
    } else {
      byLabel.set(label, { label, status: c.status, count: 1 })
    }
  }
  return Array.from(byLabel.values())
}
