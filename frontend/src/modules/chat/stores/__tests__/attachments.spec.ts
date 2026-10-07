import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clearAttachmentCache, peekAttachmentUrl } from '../../lib/attachmentBlobCache'
import type { ChatEvent, Conversation, StoredMessage, UIAttachment } from '../../types'

const agentMock = vi.hoisted(() => ({
  stream: vi.fn(),
  attach: vi.fn(),
  isActive: vi.fn(),
  stop: vi.fn(),
}))

const conversationMock = vi.hoisted(() => ({
  getWithVersions: vi.fn(),
  list: vi.fn(),
  create: vi.fn(),
}))

vi.mock('../../services/agentService', () => ({ agentService: agentMock }))
vi.mock('../../services/conversationService', () => ({ conversationService: conversationMock }))
vi.mock('../../services/attachmentService', () => ({
  attachmentService: { upload: vi.fn(), download: vi.fn() },
}))
vi.mock('@/modules/admin', () => ({ erpDatabaseService: { available: vi.fn() } }))

import { useChatStore } from '../chatStore'

const CONV_ID = '11111111-1111-1111-1111-111111111111'

function conversation(): Conversation {
  return {
    id: CONV_ID,
    user_id: 'u1',
    erp_database_id: 'db1',
    title: 'Consulta',
    title_locked: false,
    created_at: '2026-09-15T10:00:00Z',
    updated_at: '2026-09-15T10:00:00Z',
  }
}

function stored(over: Partial<StoredMessage>): StoredMessage {
  return {
    id: 'm1',
    conversation_id: CONV_ID,
    role: 'user',
    content: '',
    created_at: '2026-09-15T10:00:00Z',
    finish_reason: null,
    tool_invocations: [],
    usage: null,
    cost_usd: null,
    superseded_at: null,
    superseded_by_id: null,
    ...over,
  }
}

const serverImage = {
  id: 'att-1',
  mime: 'image/png',
  filename: 'captura.png',
  size_bytes: 10,
  width: 1,
  height: 1,
}

const local: UIAttachment = {
  id: 'att-1',
  filename: 'captura.png',
  mime: 'image/png',
  previewUrl: 'blob:local-1',
}

function doneEvents(): AsyncGenerator<ChatEvent, void, void> {
  return (async function* () {
    yield { type: 'done', usage: null, cost_usd: null, finish_reason: 'complete' } as const
  })()
}

beforeEach(() => {
  setActivePinia(createPinia())
  clearAttachmentCache()
  vi.clearAllMocks()
  agentMock.isActive.mockResolvedValue(false)
  agentMock.stream.mockImplementation(() => doneEvents())
  conversationMock.getWithVersions.mockResolvedValue({
    conversation: conversation(),
    messages: [],
  })
})

async function activeStore() {
  const store = useChatStore()
  store.activeConversationId = CONV_ID
  return store
}

describe('chatStore · imágenes adjuntas', () => {
  it('sendMessage manda attachment_ids y muestra las miniaturas locales al instante', async () => {
    const store = await activeStore()

    const turn = store.sendMessage('¿qué dice?', [local])

    const user = store.messages[0]
    expect(user?.attachments).toEqual([local])
    expect(peekAttachmentUrl('att-1')).toBe('blob:local-1')
    await turn
    expect(agentMock.stream.mock.calls[0]?.[0]).toEqual({
      conversation_id: CONV_ID,
      action: 'send',
      message: '¿qué dice?',
      attachment_ids: ['att-1'],
    })
  })

  it('un mensaje solo con imágenes no manda message', async () => {
    const store = await activeStore()

    await store.sendMessage('', [local])

    expect(agentMock.stream.mock.calls[0]?.[0]).toEqual({
      conversation_id: CONV_ID,
      action: 'send',
      attachment_ids: ['att-1'],
    })
  })

  it('sin texto ni imágenes no envía nada', async () => {
    const store = await activeStore()

    await store.sendMessage('   ', [])

    expect(agentMock.stream).not.toHaveBeenCalled()
  })

  it('sin imágenes el cuerpo queda igual que antes', async () => {
    const store = await activeStore()

    await store.sendMessage('hola')

    expect(agentMock.stream.mock.calls[0]?.[0]).toEqual({
      conversation_id: CONV_ID,
      action: 'send',
      message: 'hola',
    })
  })

  it('al hidratar, los adjuntos del servidor reemplazan a los locales', async () => {
    const store = await activeStore()
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [
        stored({ id: 'u1', content: 'hola', attachments: [serverImage] }),
        stored({ id: 'a1', role: 'assistant', content: 'listo' }),
      ],
    })

    await store.sendMessage('hola', [local])

    const user = store.messages[0]
    expect(user?.id).toBe('u1')
    expect(user?.attachments).toEqual([
      { id: 'att-1', filename: 'captura.png', mime: 'image/png', previewUrl: null },
    ])
  })

  it('editLastUserMessage manda las imágenes conservadas', async () => {
    const store = await activeStore()
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [
        stored({ id: 'u1', content: 'hola', attachments: [serverImage] }),
        stored({ id: 'a1', role: 'assistant', content: 'listo' }),
      ],
    })
    await store.loadConversation(CONV_ID)
    expect(store.messages[0]?.attachments).toHaveLength(1)

    await store.editLastUserMessage('hola editado', store.messages[0]?.attachments ?? [])

    expect(agentMock.stream.mock.calls[0]?.[0]).toEqual({
      conversation_id: CONV_ID,
      action: 'edit_last',
      message: 'hola editado',
      attachment_ids: ['att-1'],
    })
  })

  it('regenerar no toca los adjuntos del mensaje visible', async () => {
    const store = await activeStore()
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [
        stored({ id: 'u1', content: 'hola', attachments: [serverImage] }),
        stored({ id: 'a1', role: 'assistant', content: 'listo' }),
      ],
    })
    await store.loadConversation(CONV_ID)

    await store.regenerateLastAssistant()

    expect(agentMock.stream.mock.calls[0]?.[0]).toEqual({
      conversation_id: CONV_ID,
      action: 'regenerate',
    })
    expect(store.messages[0]?.attachments).toHaveLength(1)
  })

  it('si el turno se rechaza por límite, las imágenes vuelven al composer', async () => {
    const { HttpRequestError } = await import('@/lib/HttpClient')
    agentMock.stream.mockImplementation(() => ({
      [Symbol.asyncIterator]() {
        return {
          next: () =>
            Promise.reject(new HttpRequestError('límite', 429, { errorCode: 'rate_limited' })),
        }
      },
    }))
    const store = await activeStore()

    await store.sendMessage('hola', [local])

    expect(store.rejectedText).toBe('hola')
    expect(store.rejectedAttachments).toEqual([local])
    expect(store.messages).toHaveLength(0)
  })
})
