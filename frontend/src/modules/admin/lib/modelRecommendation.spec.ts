import { describe, expect, it } from 'vitest'
import { recommendModel } from './modelRecommendation'

describe('recommendModel', () => {
  it('prefers a general-purpose model over embeddings and preview models (gemini)', () => {
    const result = recommendModel(
      [
        { id: 'text-embedding-004', display_name: 'Embedding' },
        { id: 'gemini-2.5-flash-preview', display_name: 'Gemini Flash Preview' },
        { id: 'gemini-2.5-flash', display_name: 'Gemini 2.5 Flash' },
      ],
      'gemini',
    )

    expect(result?.id).toBe('gemini-2.5-flash')
  })

  it('prefers the "-latest" alias over a pinned numbered version (gemini)', () => {
    const result = recommendModel(
      [
        { id: 'gemini-3.8-flash', display_name: 'Gemini 3.8 Flash' },
        { id: 'gemini-flash-latest', display_name: 'Gemini Flash Latest' },
      ],
      'gemini',
    )

    expect(result?.id).toBe('gemini-flash-latest')
  })

  it('prefers a general GPT model over embeddings and non-conversational models (openai)', () => {
    const result = recommendModel(
      [
        { id: 'text-embedding-3-large', display_name: 'text-embedding-3-large' },
        { id: 'whisper-1', display_name: 'whisper-1' },
        { id: 'gpt-5.6-terra', display_name: 'gpt-5.6-terra' },
        { id: 'gpt-5.6-luna', display_name: 'gpt-5.6-luna' },
      ],
      'openai',
    )

    expect(result?.id.startsWith('gpt-')).toBe(true)
  })

  it('returns null for an empty catalog', () => {
    expect(recommendModel([], 'claude')).toBeNull()
  })

  it('prefers the newest Claude generation over an older one with a bigger minor number', () => {
    const result = recommendModel(
      [
        { id: 'claude-sonnet-4-6', display_name: 'Claude Sonnet 4.6' },
        { id: 'claude-sonnet-5', display_name: 'Claude Sonnet 5' },
      ],
      'claude',
    )

    expect(result?.id).toBe('claude-sonnet-5')
  })

  it('does not let a dated snapshot suffix outrank a clean generation alias (claude)', () => {
    const result = recommendModel(
      [
        { id: 'claude-opus-4-5-20251101', display_name: 'Claude Opus 4.5 (2025-11-01)' },
        { id: 'claude-sonnet-5', display_name: 'Claude Sonnet 5' },
      ],
      'claude',
    )

    expect(result?.id).toBe('claude-sonnet-5')
  })

  it('prefers Sonnet over Opus of the same generation by default (claude)', () => {
    const result = recommendModel(
      [
        { id: 'claude-opus-5', display_name: 'Claude Opus 5' },
        { id: 'claude-sonnet-5', display_name: 'Claude Sonnet 5' },
      ],
      'claude',
    )

    expect(result?.id).toBe('claude-sonnet-5')
  })
})
