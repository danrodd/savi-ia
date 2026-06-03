/**
 * Generación y descarga de CSV — autocontenido en el módulo `usage` para
 * no acoplarse a utilidades de otras features todavía sin commitear.
 */

type Cell = string | number | null | undefined

function escapeCell(value: Cell): string {
  const s = value === null || value === undefined ? '' : String(value)
  // Entrecomilla si hay coma, comilla o salto de línea; duplica comillas.
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(headers: string[], rows: Cell[][]): string {
  const lines = [headers.map(escapeCell).join(',')]
  for (const row of rows) lines.push(row.map(escapeCell).join(','))
  return lines.join('\n')
}

export function downloadCsv(filename: string, content: string): void {
  // El BOM (﻿) hace que Excel detecte UTF-8 y no rompa los acentos.
  const blob = new Blob([`﻿${content}`], {
    type: 'text/csv;charset=utf-8;',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
