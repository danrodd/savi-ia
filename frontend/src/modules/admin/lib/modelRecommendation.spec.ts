import { describe, expect, it } from 'vitest'
import { recommendModel } from './modelRecommendation'

describe('recommendModel', () => {
  it('prefers a general-purpose model over embeddings and preview models', () => {
    const result = recommendModel([
      { id: 'text-embedding-004', display_name: 'Embedding' },
      { id: 'gemini-2.5-flash-preview', display_name: 'Gemini Flash Preview' },
      { id: 'gemini-2.5-flash', display_name: 'Gemini 2.5 Flash' },
    ])

    expect(result?.id).toBe('gemini-2.5-flash')
  })

  it('returns null for an empty catalog', () => {
    expect(recommendModel([])).toBeNull()
  })
})
