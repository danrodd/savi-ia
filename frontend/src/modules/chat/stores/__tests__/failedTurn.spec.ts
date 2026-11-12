/**
 * Un turno que falló queda en el historial con su mensaje y su código de
 * soporte (P4 de los hallazgos de la primera demo).
 *
 * En la demo, dos preguntas quedaron sin respuesta al recargar porque el turno
 * fallido no se guardaba. Ahora el backend lo guarda y la pantalla lo muestra
 * con el texto de su categoría, el código y Regenerar.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatEvent, Conversation, StoredMessage } from '../../types'

const agentMock = vi.hoisted(() => ({
  stream: vi.fn(),
  attach: vi.fn(),
  isActive: vi.fn(),
  stop: vi.fn(),
}))

const conversationMock = vi.hoisted(() => ({
  getWithVersions: vi.fn(),
  list: vi.fn(),
}))

vi.mock('../../services/agentService', () => ({ agentService: agentMock }))
vi.mock('../../services/conversationService', () => ({ conversationService: conversationMock }))
vi.mock('@/modules/admin', () => ({ erpDatabaseService: { available: vi.fn() } }))

import { useChatStore } from '../chatStore'

const CONV_ID = '11111111-1111-1111-1111-111111111111'
const BUSY =
  'El servicio de inteligencia artificial está saturado en este momento. Espere un minuto y toque Regenerar.'

function conversation(): Conversation {
  return {
    id: CONV_ID,
    user_id: 'u1',
    erp_database_id: 'db1',
    title: 'Inventario',
    title_locked: false,
    created_at: '2026-11-11T16:30:00Z',
    updated_at: '2026-11-11T16:30:00Z',
  }
}

function message(over: Partial<StoredMessage>): StoredMessage {
  return {
    id: 'm1',
    conversation_id: CONV_ID,
    role: 'user',
    content: 'Productos sin movimiento',
    created_at: '2026-11-11T16:30:00Z',
    finish_reason: null,
    tool_invocations: [],
    usage: null,
    cost_usd: null,
    superseded_at: null,
    superseded_by_id: null,
    ...over,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  agentMock.isActive.mockResolvedValue(false)
})

describe('turno fallido guardado', () => {
  it('se muestra al recargar con su mensaje, su código y Regenerar', async () => {
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [
        message({}),
        message({
          id: 'm2',
          role: 'assistant',
          content: '',
          finish_reason: 'error',
          error_code: 'provider_busy',
          error_message: BUSY,
          support_code: 'A1B2C3D4',
        }),
      ],
    })
    const store = useChatStore()

    await store.loadConversation(CONV_ID)

    const last = store.messages[store.messages.length - 1]
    expect(last?.error).toBe(BUSY)
    expect(last?.supportCode).toBe('A1B2C3D4')
    expect(store.canRegenerate).toBe(true)
  })

  it('un fallo guardado por un backend anterior, sin texto, igual se explica', async () => {
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [
        message({}),
        message({ id: 'm2', role: 'assistant', content: '', finish_reason: 'error' }),
      ],
    })
    const store = useChatStore()

    await store.loadConversation(CONV_ID)

    expect(store.messages[1]?.error).toContain('Regenerar')
  })

  it('el error en vivo trae el código de soporte', async () => {
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [],
    })
    agentMock.stream.mockImplementation(async function* () {
      yield {
        type: 'error',
        message: BUSY,
        code: 'provider_busy',
        support_code: 'FFEE0011',
      } satisfies ChatEvent
    })
    const store = useChatStore()
    await store.loadConversation(CONV_ID)

    await store.sendMessage('Productos sin movimiento')

    const last = store.messages[store.messages.length - 1]
    expect(last?.error).toBe(BUSY)
    expect(last?.supportCode).toBe('FFEE0011')
  })
})
