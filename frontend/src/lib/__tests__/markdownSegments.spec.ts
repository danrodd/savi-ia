import { describe, expect, it } from 'vitest'
import { parseSegments } from '../markdownSegments'

describe('parseSegments', () => {
  it('returns a single prose segment for plain markdown', () => {
    const segs = parseSegments('# Hola\n\nUn párrafo.')
    expect(segs).toEqual([{ type: 'prose', content: '# Hola\n\nUn párrafo.' }])
  })

  it('extracts a savi-chart block as a chart segment', () => {
    const src = 'Antes\n\n```savi-chart\n{"type":"bar"}\n```\n\nDespués'
    const segs = parseSegments(src)
    expect(segs).toHaveLength(3)
    expect(segs[0]).toEqual({ type: 'prose', content: 'Antes\n' })
    expect(segs[1]).toEqual({ type: 'chart', content: '{"type":"bar"}' })
    expect(segs[2]).toEqual({ type: 'prose', content: '\nDespués' })
  })

  it('extracts a mermaid block as a mermaid segment', () => {
    const segs = parseSegments('```mermaid\nflowchart LR\nA-->B\n```')
    expect(segs).toEqual([{ type: 'mermaid', content: 'flowchart LR\nA-->B' }])
  })

  it('leaves a normal code block inside prose', () => {
    const src = '```ts\nconst x = 1\n```'
    const segs = parseSegments(src)
    expect(segs).toEqual([{ type: 'prose', content: src }])
  })

  it('keeps an unterminated chart block as prose (streaming safety)', () => {
    const src = 'Texto\n\n```savi-chart\n{"type":"ba'
    const segs = parseSegments(src)
    expect(segs).toHaveLength(1)
    expect(segs[0]?.type).toBe('prose')
    expect(segs[0]?.content).toContain('savi-chart')
  })

  it('handles multiple special blocks interleaved with prose', () => {
    const src = ['```savi-chart', '{"a":1}', '```', 'medio', '```mermaid', 'graph TD', '```'].join(
      '\n',
    )
    const segs = parseSegments(src)
    expect(segs.map((s) => s.type)).toEqual(['chart', 'prose', 'mermaid'])
  })
})
