/**
 * Parte una respuesta markdown en segmentos ordenados para renderizar prosa y
 * bloques interactivos por separado.
 *
 * ¿Por qué? El render actual es `markdown-it → DOMPurify → v-html`: un string
 * HTML. Una gráfica (ECharts) o un diagrama (Mermaid) necesitan un nodo DOM
 * real + JS de init, no viven en ese string. Así que aislamos los bloques
 * ```savi-chart``` y ```mermaid``` como segmentos propios; el resto es prosa.
 *
 * Seguro para streaming: un bloque especial sin cerrar todavía (el ``` final
 * no llegó) se devuelve como prosa cruda — nunca intentamos parsear JSON a
 * medias. Cuando el stream cierra el bloque, pasa a ser segmento de gráfica.
 */

export type Segment =
  | { type: 'prose'; content: string }
  | { type: 'chart'; content: string }
  | { type: 'mermaid'; content: string }

const SPECIAL_LANGS: Record<string, 'chart' | 'mermaid'> = {
  'savi-chart': 'chart',
  mermaid: 'mermaid',
}

const OPEN_FENCE = /^(\s*)(`{3,}|~{3,})\s*([\w-]*)\s*$/
const CLOSE_FENCE = /^(\s*)(`{3,}|~{3,})\s*$/

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

    if (!open) {
      prose.push(line)
      i++
      continue
    }

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
      // Bloque especial completo → segmento propio.
      flushProse()
      const inner = lines.slice(i + 1, close).join('\n')
      segments.push({ type: special, content: inner })
      i = close + 1
      continue
    }

    // Bloque normal (o especial aún sin cerrar) → queda como prosa cruda.
    // Si no cerró, arrastramos hasta el final (caso streaming).
    const end = close === -1 ? lines.length - 1 : close
    for (let j = i; j <= end; j++) prose.push(lines[j] ?? '')
    i = end + 1
  }

  flushProse()
  return segments
}
