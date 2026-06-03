import { describe, expect, it } from 'vitest'
import { parseChartSpec } from '../chartSpec'

describe('parseChartSpec', () => {
  it('accepts a valid bar spec', () => {
    const raw = JSON.stringify({
      type: 'bar',
      title: 'Ventas',
      labels: ['Ene', 'Feb'],
      series: [{ name: 'Ventas', data: [10, 20] }],
    })
    const res = parseChartSpec(raw)
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.spec.type).toBe('bar')
  })

  it('rejects invalid JSON', () => {
    const res = parseChartSpec('{ not json')
    expect(res).toEqual({ ok: false, error: 'JSON inválido' })
  })

  it('rejects an unknown chart type', () => {
    const res = parseChartSpec(JSON.stringify({ type: 'donut', series: [{ data: [1] }] }))
    expect(res.ok).toBe(false)
  })

  it('rejects a spec without series', () => {
    const res = parseChartSpec(JSON.stringify({ type: 'line' }))
    expect(res.ok).toBe(false)
  })

  it('rejects non-numeric data', () => {
    const res = parseChartSpec(JSON.stringify({ type: 'line', series: [{ data: ['a', 'b'] }] }))
    expect(res.ok).toBe(false)
  })

  it('accepts a pie spec with labels', () => {
    const raw = JSON.stringify({
      type: 'pie',
      labels: ['A', 'B', 'C'],
      series: [{ data: [30, 50, 20] }],
    })
    const res = parseChartSpec(raw)
    expect(res.ok).toBe(true)
  })
})
