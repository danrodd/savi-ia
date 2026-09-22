import { describe, expect, it } from 'vitest'
import { presetToRange, toLocalIsoDate } from './dateRange'

// Miércoles 2026-09-16, 23:30 hora local — cerca de medianoche a propósito.
const NOW = new Date(2026, 8, 16, 23, 30)

describe('toLocalIsoDate', () => {
  it('formats using local calendar components, not UTC', () => {
    expect(toLocalIsoDate(NOW)).toBe('2026-09-16')
  })
})

describe('presetToRange', () => {
  it('today covers only the current local day', () => {
    const range = presetToRange('today', { from: '', to: '' }, NOW)
    expect(range).toEqual({ from: '2026-09-16', to: '2026-09-16' })
  })

  it('yesterday covers only the previous local day', () => {
    const range = presetToRange('yesterday', { from: '', to: '' }, NOW)
    expect(range).toEqual({ from: '2026-09-15', to: '2026-09-15' })
  })

  it('7 spans the last 7 local days including today', () => {
    const range = presetToRange(7, { from: '', to: '' }, NOW)
    expect(range).toEqual({ from: '2026-09-10', to: '2026-09-16' })
  })

  it('30 spans the last 30 local days including today', () => {
    const range = presetToRange(30, { from: '', to: '' }, NOW)
    expect(range).toEqual({ from: '2026-08-18', to: '2026-09-16' })
  })

  it('custom passes the given dates through unchanged', () => {
    const range = presetToRange('custom', { from: '2025-01-01', to: '2025-01-31' }, NOW)
    expect(range).toEqual({ from: '2025-01-01', to: '2025-01-31' })
  })

  it('does not roll over into the next month across a month boundary', () => {
    const firstOfMonth = new Date(2026, 2, 1, 10, 0) // 2026-03-01
    const range = presetToRange('yesterday', { from: '', to: '' }, firstOfMonth)
    expect(range).toEqual({ from: '2026-02-28', to: '2026-02-28' })
  })
})
