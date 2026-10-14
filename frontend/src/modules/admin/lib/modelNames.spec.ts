import { describe, expect, it } from 'vitest'
import { friendlyModelName } from './modelNames'

describe('friendlyModelName', () => {
  it.each([
    ['gpt-6-luna', 'GPT-6 Luna'],
    ['gpt-6.1-sol', 'GPT-6.1 Sol'],
    ['gpt-4o-mini', 'GPT-4o Mini'],
    ['gpt-4o-2024-08-06', 'GPT-4o'],
    ['claude-sonnet-5', 'Claude Sonnet 5'],
    ['claude-opus-5', 'Claude Opus 5'],
    ['claude-haiku-4-5-20251001', 'Claude Haiku 4.5'],
    ['claude-haiku-4-5', 'Claude Haiku 4.5'],
    ['claude-3-5-sonnet-20241022', 'Claude Sonnet 3.5'],
    ['gemini-flash-lite-latest', 'Gemini Flash Lite'],
    ['gemini-2.5-flash', 'Gemini 2.5 Flash'],
  ])('%s → %s', (id, expected) => {
    expect(friendlyModelName(id)).toBe(expected)
  })

  it('un identificador que no conoce se devuelve tal cual', () => {
    expect(friendlyModelName('mistral-large-2')).toBe('mistral-large-2')
    expect(friendlyModelName('gemini-2.5-flash-preview-05-20')).toBe(
      'gemini-2.5-flash-preview-05-20',
    )
  })

  it('tolera vacío', () => {
    expect(friendlyModelName(null)).toBe('')
    expect(friendlyModelName('')).toBe('')
  })
})
