import { describe, expect, it } from 'vitest'
import type { DailyUsage } from '../types'
import { dailyQueryBars, periodDescription } from './simpleUsage'

function day(date: string, messages: number): DailyUsage {
  return {
    day: date,
    totals: {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
      total_tokens: 0,
      message_count: messages,
      cost_usd: 0,
      untariffed_count: 0,
    },
  }
}

describe('dailyQueryBars', () => {
  it('ordena por fecha y escala contra el día con más consultas', () => {
    const bars = dailyQueryBars([day('2026-10-03', 2), day('2026-10-01', 8), day('2026-10-02', 4)])

    expect(bars.map((b) => [b.day, b.count, b.percent])).toEqual([
      ['2026-10-01', 8, 100],
      ['2026-10-02', 4, 50],
      ['2026-10-03', 2, 25],
    ])
  })

  it('con todo en cero no divide por cero', () => {
    expect(dailyQueryBars([day('2026-10-01', 0)])[0]?.percent).toBe(0)
  })
})

describe('periodDescription', () => {
  it('describe el rango elegido en lenguaje común', () => {
    expect(periodDescription('today')).toBe('Hoy')
    expect(periodDescription(30)).toBe('En los últimos 30 días')
    expect(periodDescription('custom')).toBe('En el período elegido')
  })
})
