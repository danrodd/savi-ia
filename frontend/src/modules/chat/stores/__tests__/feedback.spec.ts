import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { StoredMessage, UIMessage } from '../../types'

const feedbackMock = vi.hoisted(() => ({ set: vi.fn(), clear: vi.fn() }))

vi.mock('../../services/feedbackService', () => ({ feedbackService: feedbackMock }))
vi.mock('../../services/agentService', () => ({
  agentService: { stream: vi.fn(), attach: vi.fn(), isActive: vi.fn(), stop: vi.fn() },
}))
vi.mock('../../services/conversationService', () => ({
  conversationService: { getWithVersions: vi.fn(), get: vi.fn(), list: vi.fn(), create: vi.fn() },
}))
vi.mock('../../services/attachmentService', () => ({
  attachmentService: { upload: vi.fn(), download: vi.fn() },
}))
vi.mock('@/modules/admin', () => ({ erpDatabaseService: { available: vi.fn() } }))

import { conversationService } from '../../services/conversationService'
import { useChatStore } from '../chatStore'

const CONV_ID = 'conv-1'

function assistant(over: Partial<UIMessage> = {}): UIMessage {
  return {
    tempId: 'a1',
    id: 'a1',
    role: 'assistant',
    text: 'Vendiste 10 millones.',
    toolCalls: [],
    done: true,
    feedback: null,
    ...over,
  }
}

function setup(message: UIMessage = assistant()) {
  const store = useChatStore()
  store.activeConversationId = CONV_ID
  store.messages = [message]
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  feedbackMock.set.mockResolvedValue({})
  feedbackMock.clear.mockResolvedValue(undefined)
})

describe('chatStore · rateMessage', () => {
  it('muestra la calificación al instante y la guarda', async () => {
    const store = setup()

    const pending = store.rateMessage('a1', { rating: 'up' })

    expect(store.messages[0]?.feedback).toEqual({ rating: 'up', reason: null, comment: null })
    expect(await pending).toBe(true)
    expect(feedbackMock.set).toHaveBeenCalledWith(CONV_ID, 'a1', {
      rating: 'up',
      reason: null,
      comment: null,
    })
  })

  it('un 👎 lleva el motivo y el comentario recortado', async () => {
    const store = setup()

    await store.rateMessage('a1', {
      rating: 'down',
      reason: 'incompleta',
      comment: '  Faltó el IVA  ',
    })

    expect(store.messages[0]?.feedback).toEqual({
      rating: 'down',
      reason: 'incompleta',
      comment: 'Faltó el IVA',
    })
  })

  it('un 👍 nunca arrastra motivo ni comentario', async () => {
    const store = setup()

    await store.rateMessage('a1', { rating: 'up', reason: 'otra', comment: 'x' })

    expect(store.messages[0]?.feedback).toEqual({ rating: 'up', reason: null, comment: null })
  })

  it('vuelve al valor anterior si el backend rechaza', async () => {
    const previous = { rating: 'up' as const, reason: null, comment: null }
    const store = setup(assistant({ feedback: previous }))
    feedbackMock.set.mockRejectedValue(new Error('boom'))

    const ok = await store.rateMessage('a1', { rating: 'down', reason: 'otra' })

    expect(ok).toBe(false)
    expect(store.messages[0]?.feedback).toEqual(previous)
  })

  it('con null quita la calificación y llama a DELETE', async () => {
    const store = setup(assistant({ feedback: { rating: 'up', reason: null, comment: null } }))

    expect(await store.rateMessage('a1', null)).toBe(true)

    expect(store.messages[0]?.feedback).toBeNull()
    expect(feedbackMock.clear).toHaveBeenCalledWith(CONV_ID, 'a1')
    expect(feedbackMock.set).not.toHaveBeenCalled()
  })

  it('si quitarla falla, la calificación sigue ahí', async () => {
    const current = { rating: 'down' as const, reason: 'muy_lenta' as const, comment: null }
    const store = setup(assistant({ feedback: current }))
    feedbackMock.clear.mockRejectedValue(new Error('boom'))

    expect(await store.rateMessage('a1', null)).toBe(false)

    expect(store.messages[0]?.feedback).toEqual(current)
  })

  it('un mensaje desconocido no llama al backend', async () => {
    const store = setup()

    expect(await store.rateMessage('otro', { rating: 'up' })).toBe(false)

    expect(feedbackMock.set).not.toHaveBeenCalled()
  })

  it('el historial trae la calificación en el mensaje', async () => {
    const stored: StoredMessage = {
      id: 'a1',
      conversation_id: CONV_ID,
      role: 'assistant',
      content: 'Hola',
      created_at: '2026-10-13T10:00:00Z',
      finish_reason: 'complete',
      tool_invocations: [],
      usage: null,
      cost_usd: null,
      superseded_at: null,
      superseded_by_id: null,
      feedback: { rating: 'down', reason: 'dato_incorrecto', comment: 'Mal' },
    }
    vi.mocked(conversationService.getWithVersions).mockResolvedValue({
      conversation: {
        id: CONV_ID,
        user_id: null,
        erp_database_id: null,
        title: 'Hilo',
        title_locked: false,
        created_at: stored.created_at,
        updated_at: stored.created_at,
      },
      messages: [stored],
    })
    vi.mocked(conversationService.get).mockResolvedValue({
      conversation: {
        id: CONV_ID,
        user_id: null,
        erp_database_id: null,
        title: 'Hilo',
        title_locked: false,
        created_at: stored.created_at,
        updated_at: stored.created_at,
      },
      messages: [stored],
    })
    const store = useChatStore()

    await store.loadConversation(CONV_ID)

    expect(store.messages[0]?.feedback).toEqual({
      rating: 'down',
      reason: 'dato_incorrecto',
      comment: 'Mal',
    })
  })
})
