import { describe, expect, it } from 'vitest'

import type { DatabaseUsage, UsageTotals } from '../types'
import { buildDatabaseRows, databaseLabel } from './databases'

const FRAMI = { id: 'b614363b-0b1c-46fc-b272-767321c1e092', code: 'FRAMI', name: 'frami' }
const SUR = { id: 'd833414a-c6b4-4305-8710-dad61960b2f3', code: 'SUR_ANDINA', name: 'sur_andina' }

function totals(costUsd: number, messages = 1): UsageTotals {
  return {
    input_tokens: 10,
    output_tokens: 5,
    cache_read_input_tokens: 0,
    cache_creation_input_tokens: 0,
    total_tokens: 15,
    message_count: messages,
    cost_usd: costUsd,
    untariffed_count: 0,
  }
}

describe('databaseLabel', () => {
  it('uses the database code', () => {
    expect(databaseLabel(FRAMI.id, [FRAMI, SUR])).toBe('FRAMI')
  })

  it('labels legacy conversations without a database', () => {
    expect(databaseLabel(null, [FRAMI])).toBe('Sin base (legado)')
  })

  it('keeps an unknown database traceable by a short id', () => {
    expect(databaseLabel('f736cb27-af2f-4682-a616-641c2e6ea4d4', [FRAMI])).toBe('Base f736cb27')
  })
})

describe('buildDatabaseRows', () => {
  it('computes each client share of the period cost', () => {
    const rows: DatabaseUsage[] = [
      { erp_database_id: FRAMI.id, totals: totals(3, 6) },
      { erp_database_id: SUR.id, totals: totals(1, 2) },
    ]

    const result = buildDatabaseRows(rows, [FRAMI, SUR])

    expect(result.map((r) => [r.label, r.responses, r.share])).toEqual([
      ['FRAMI', 6, 75],
      ['SUR_ANDINA', 2, 25],
    ])
  })

  it('does not divide by zero when nothing was charged', () => {
    const result = buildDatabaseRows([{ erp_database_id: FRAMI.id, totals: totals(0) }], [FRAMI])

    expect(result[0]?.share).toBe(0)
  })
})
