/**
 * Serialización de filas a CSV con dos cuidados:
 *
 * 1. **Inyección de fórmulas (CSV injection)**: una celda que arranca con
 *    `=`, `+`, `-`, `@`, tab o CR puede ejecutar una fórmula al abrir el
 *    archivo en Excel/Sheets. La neutralizamos con un apóstrofo inicial.
 *    Crítico: estos datos salen de un ERP y los abre gente en Excel.
 * 2. **Escapado RFC 4180**: celdas con coma, comilla o salto de línea van
 *    entre comillas dobles, duplicando las comillas internas.
 */

const FORMULA_START = /^[=+\-@\t\r]/
const NEEDS_QUOTING = /[",\n\r]/

function sanitizeFormula(value: string): string {
  return FORMULA_START.test(value) ? `'${value}` : value
}

function escapeCell(value: string): string {
  return NEEDS_QUOTING.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

/** Convierte una matriz de filas (la primera es el encabezado) en CSV. */
export function toCsv(rows: string[][]): string {
  return rows
    .map((row) => row.map((cell) => escapeCell(sanitizeFormula(cell))).join(','))
    .join('\r\n')
}
