/**
 * Parte una respuesta markdown en segmentos ordenados para renderizar prosa y
 * bloques interactivos por separado.
 *
 * ¿Por qué? El render actual es `markdown-it → DOMPurify → v-html`: un string
 * HTML. Una gráfica (ECharts), un diagrama (Mermaid) o una tabla con botón de
 * descarga necesitan un nodo DOM real / datos estructurados, no viven en ese
 * string. Así que aislamos los bloques ```savi-chart```, ```mermaid``` y las
 * tablas markdown como segmentos propios; el resto es prosa.
 *
 * Seguro para streaming: un bloque especial sin cerrar todavía (el ``` final
 * no llegó) se devuelve como prosa cruda — nunca intentamos parsear JSON a
 * medias. Una tabla a la que aún no llegó la fila separadora tampoco se
 * detecta: queda como prosa hasta estar completa.
 */

export type Segment =
  | { type: 'prose'; content: string }
  | { type: 'chart'; content: string }
  | { type: 'mermaid'; content: string }
  | { type: 'table'; rows: string[][] }

const SPECIAL_LANGS: Record<string, 'chart' | 'mermaid'> = {
  'savi-chart': 'chart',
  mermaid: 'mermaid',
}

const OPEN_FENCE = /^(\s*)(`{3,}|~{3,})\s*([\w-]*)\s*$/
const CLOSE_FENCE = /^(\s*)(`{3,}|~{3,})\s*$/
// Fila separadora de tabla GFM: celdas de guiones (con `:` opcional) y al
// menos un `|` — el `|` la distingue de un `---` (regla horizontal).
const TABLE_SEPARATOR = /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$/

function splitRow(line: string): string[] {
  let t = line.trim()
  if (t.startsWith('|')) t = t.slice(1)
  if (t.endsWith('|')) t = t.slice(0, -1)
  return t.split('|').map((c) => c.trim())
}

function isSeparator(line: string): boolean {
  const t = line.trim()
  return t.includes('|') && TABLE_SEPARATOR.test(t)
}

/** Detecta una tabla GFM a partir de `start`. Devuelve filas + índice final. */
function tryParseTable(lines: string[], start: number): { rows: string[][]; end: number } | null {
  const header = lines[start] ?? ''
  const sep = lines[start + 1] ?? ''
  if (!header.includes('|') || !isSeparator(sep)) return null

  const rows: string[][] = [splitRow(header)]
  let j = start + 2
  for (; j < lines.length; j++) {
    const l = lines[j] ?? ''
    if (l.trim() === '' || !l.includes('|')) break
    rows.push(splitRow(l))
  }
  return { rows, end: j - 1 }
}

export function parseSegments(source: string): Segment[] {
  const lines = source.split('\n')
  const segments: Segment[] = []
  let prose: string[] = []

  function flushProse(): void {
    if (prose.length === 0) return
    const text = prose.join('\n')
    if (text.trim()) segments.push({ type: 'prose', content: text })
    prose = []
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i] ?? ''
    const open = OPEN_FENCE.exec(line)

    if (open) {
      const fence = open[2] ?? ''
      const fenceChar = fence.charAt(0)
      const fenceLen = fence.length
      const special = SPECIAL_LANGS[(open[3] ?? '').toLowerCase()]

      // Busca el cierre del bloque (mismo carácter, longitud ≥ apertura).
      let close = -1
      for (let j = i + 1; j < lines.length; j++) {
        const m = CLOSE_FENCE.exec(lines[j] ?? '')
        if (!m) continue
        const cf = m[2] ?? ''
        if (cf.charAt(0) === fenceChar && cf.length >= fenceLen) {
          close = j
          break
        }
      }

      if (special && close !== -1) {
        flushProse()
        const inner = lines.slice(i + 1, close).join('\n')
        segments.push({ type: special, content: inner })
        i = close + 1
        continue
      }

      // Bloque normal (o especial aún sin cerrar) → prosa cruda. Si no cerró,
      // arrastramos hasta el final (caso streaming).
      const end = close === -1 ? lines.length - 1 : close
      for (let j = i; j <= end; j++) prose.push(lines[j] ?? '')
      i = end + 1
      continue
    }

    // Tabla markdown → segmento propio con datos estructurados.
    const table = tryParseTable(lines, i)
    if (table) {
      flushProse()
      segments.push({ type: 'table', rows: table.rows })
      i = table.end + 1
      continue
    }

    prose.push(line)
    i++
  }

  flushProse()
  return segments
}
