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

  it('prefers a general GPT model over embeddings and non-conversational models', () => {
    const result = recommendModel([
      { id: 'text-embedding-3-large', display_name: 'text-embedding-3-large' },
      { id: 'whisper-1', display_name: 'whisper-1' },
      { id: 'gpt-5.6-terra', display_name: 'gpt-5.6-terra' },
      { id: 'gpt-5.6-luna', display_name: 'gpt-5.6-luna' },
    ])

    expect(result?.id.startsWith('gpt-')).toBe(true)
  })

  it('returns null for an empty catalog', () => {
    expect(recommendModel([])).toBeNull()
  })
})
