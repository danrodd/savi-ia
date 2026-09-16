/**
 * El turno vive en el servidor, no en la conexión.
 *
 * Lo que se prueba acá es la consecuencia visible: salir de la conversación no
 * marca la respuesta como interrumpida, volver se reengancha a lo que se está
 * generando, y "Detener" le avisa al servidor en lugar de solo cortar el
 * fetch. Ver `docs/chat-turnos-en-segundo-plano.md`.
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

function userMessage(): StoredMessage {
  return {
    id: 'm1',
    conversation_id: CONV_ID,
    role: 'user',
    content: '¿Cuánto vendimos ayer?',
    created_at: '2026-09-15T10:00:00Z',
    finish_reason: null,
    tool_invocations: [],
    usage: null,
    cost_usd: null,
    superseded_at: null,
    superseded_by_id: null,
  }
}

function assistantMessage(text: string): StoredMessage {
  return { ...userMessage(), id: 'm2', role: 'assistant', content: text }
}

/**
 * Turno en curso: emite unos eventos y se queda esperando hasta que aborten la
 * señal, igual que el `fetch` real.
 */
function streamControlado(eventos: ChatEvent[]) {
  return async function* (
    _body: unknown,
    signal: AbortSignal,
  ): AsyncGenerator<ChatEvent, void, void> {
    for (const ev of eventos) yield ev
    await new Promise<void>((_, reject) => {
      const fallar = () => {
        const abortado = new Error('aborted')
        abortado.name = 'AbortError'
        reject(abortado)
      }
      // Hay que mirar `aborted` antes de suscribirse: si el corte llegó
      // mientras se consumían los eventos, el evento ya pasó y esperarlo sería
      // esperar para siempre.
      if (signal.aborted) fallar()
      else signal.addEventListener('abort', fallar, { once: true })
    })
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  conversationMock.getWithVersions.mockResolvedValue({
    conversation: conversation(),
    messages: [userMessage()],
  })
  agentMock.isActive.mockResolvedValue(false)
  agentMock.stop.mockResolvedValue(undefined)
})

describe('reenganche al abrir una conversación', () => {
  it('no pide el stream si no hay nada en curso', async () => {
    const store = useChatStore()

    await store.loadConversation(CONV_ID)

    expect(agentMock.attach).not.toHaveBeenCalled()
    expect(store.messages).toHaveLength(1)
  })

  it('se engancha y pinta lo que ya se había generado', async () => {
    agentMock.isActive.mockResolvedValue(true)
    agentMock.attach.mockImplementation(async function* () {
      yield { type: 'text_delta', text: 'Ayer ' } satisfies ChatEvent
      yield { type: 'text_delta', text: 'vendiste $1.200.' } satisfies ChatEvent
      yield {
        type: 'done',
        usage: null,
        cost_usd: null,
        finish_reason: 'complete',
      } satisfies ChatEvent
    })
    const store = useChatStore()

    await store.loadConversation(CONV_ID)

    const last = store.messages[store.messages.length - 1]
    expect(last?.role).toBe('assistant')
    expect(last?.text).toBe('Ayer vendiste $1.200.')
    expect(last?.done).toBe(true)
    expect(last?.interrupted).toBeUndefined()
  })

  it('si el turno ya terminó, no deja un mensaje vacío ni un error rojo', async () => {
    agentMock.isActive.mockResolvedValue(true)
    agentMock.attach.mockImplementation(async function* (): AsyncGenerator<ChatEvent, void, void> {
      throw new Error('No hay una respuesta en curso en esta conversación.')
    })
    const store = useChatStore()

    await store.loadConversation(CONV_ID)

    expect(store.messages).toHaveLength(1)
    expect(store.error).toBeNull()
  })
})

describe('salir de la conversación', () => {
  it('no marca la respuesta como interrumpida: el turno sigue vivo', async () => {
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [userMessage(), assistantMessage('Estoy pens')],
    })
    agentMock.stream.mockImplementation(streamControlado([{ type: 'text_delta', text: 'Estoy pens' }]))
    const store = useChatStore()
    store.activeConversationId = CONV_ID

    const enCurso = store.sendMessage('hola')
    await vi.waitFor(() => expect(store.messages.at(-1)?.text).toBe('Estoy pens'))

    store.detachStream()
    await enCurso

    expect(agentMock.stop).not.toHaveBeenCalled()
    const last = store.messages[store.messages.length - 1]
    expect(last?.interrupted).toBeUndefined()
  })
})

describe('"Detener"', () => {
  it('le avisa al servidor y recién ahí marca la respuesta interrumpida', async () => {
    conversationMock.getWithVersions.mockResolvedValue({
      conversation: conversation(),
      messages: [userMessage(), assistantMessage('Estoy pens')],
    })
    agentMock.stream.mockImplementation(streamControlado([{ type: 'text_delta', text: 'Estoy pens' }]))
    const store = useChatStore()
    store.activeConversationId = CONV_ID

    const enCurso = store.sendMessage('hola')
    await vi.waitFor(() => expect(store.messages.at(-1)?.text).toBe('Estoy pens'))

    await store.stopStream()
    await enCurso

    expect(agentMock.stop).toHaveBeenCalledWith(CONV_ID)
    const last = store.messages[store.messages.length - 1]
    expect(last?.interrupted).toBe(true)
  })

  it('no le pega al backend si no hay nada generándose', async () => {
    const store = useChatStore()

    await store.stopStream()

    expect(agentMock.stop).not.toHaveBeenCalled()
  })
})
