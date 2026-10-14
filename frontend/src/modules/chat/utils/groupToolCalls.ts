import type { ToolCall, ToolCallGroup } from '../types'
import { getKindLabel, getToolKind } from './toolLabels'

/**
 * Agrupa tool calls por el tipo de consulta que verá el usuario, preservando
 * el orden de primera aparición. Tools distintas del mismo tipo (p.ej.
 * `consultar_libre` y `consultar_datos` → "ERP") se fusionan en una sola
 * pastilla con contador.
 *
 * El status agregado prioriza running > error > success — así un grupo
 * donde aún corre alguna tool se muestra activo aunque otras ya hayan
 * terminado, y un error parcial no se enmascara con un éxito posterior. El
 * texto se calcula con el status agregado, ya en gerundio o en pasado.
 */
export function groupToolCalls(calls: ToolCall[]): ToolCallGroup[] {
  const byKind = new Map<string, ToolCallGroup>()
  for (const c of calls) {
    const kind = getToolKind(c.name, c.input)
    const existing = byKind.get(kind)
    if (existing) {
      existing.count++
      if (c.status === 'running') existing.status = 'running'
      else if (c.status === 'error' && existing.status !== 'running') existing.status = 'error'
    } else {
      byKind.set(kind, { kind, label: '', status: c.status, count: 1 })
    }
  }
  const groups = Array.from(byKind.values())
  for (const g of groups) g.label = getKindLabel(g.kind, g.status)
  return groups
}
