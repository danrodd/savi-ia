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
    const first = segs[0]
    expect(first?.type).toBe('prose')
    if (first?.type === 'prose') expect(first.content).toContain('savi-chart')
  })

  it('handles multiple special blocks interleaved with prose', () => {
    const src = ['```savi-chart', '{"a":1}', '```', 'medio', '```mermaid', 'graph TD', '```'].join(
      '\n',
    )
    const segs = parseSegments(src)
    expect(segs.map((s) => s.type)).toEqual(['chart', 'prose', 'mermaid'])
  })

  it('extracts a markdown table as a table segment with parsed rows', () => {
    const src = [
      '| Cliente | Total |',
      '|---|---|',
      '| Farmacia X | 100 |',
      '| Droguería Y | 50 |',
    ].join('\n')
    const segs = parseSegments(src)
    expect(segs).toHaveLength(1)
    expect(segs[0]).toEqual({
      type: 'table',
      rows: [
        ['Cliente', 'Total'],
        ['Farmacia X', '100'],
        ['Droguería Y', '50'],
      ],
    })
  })

  it('keeps prose around a table', () => {
    const src = [
      'Top de clientes:',
      '',
      '| A | B |',
      '|---|---|',
      '| 1 | 2 |',
      '',
      'Eso es todo.',
    ].join('\n')
    const segs = parseSegments(src)
    expect(segs.map((s) => s.type)).toEqual(['prose', 'table', 'prose'])
  })

  it('does not mistake a horizontal rule for a table', () => {
    const segs = parseSegments('Texto\n\n---\n\nMás texto')
    expect(segs.every((s) => s.type === 'prose')).toBe(true)
  })

  it('does not detect a table until the separator row arrives (streaming)', () => {
    const segs = parseSegments('| A | B |')
    expect(segs).toEqual([{ type: 'prose', content: '| A | B |' }])
  })
})
