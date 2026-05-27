import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { agentService } from '../services/agentService'
import { conversationService } from '../services/conversationService'
import type {
  ChatEvent,
  Conversation,
  StoredMessage,
  ToolCall,
  ToolInvocation,
  UIMessage,
} from '../types'

function mapStoredToolCall(t: ToolInvocation): ToolCall {
  const status: ToolCall['status'] =
    t.status === 'ok' ? 'success' : t.status === 'error' ? 'error' : 'success'
  return { id: t.id, name: t.name, status }
}

function toUIMessages(stored: StoredMessage[]): UIMessage[] {
  return stored
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => {
      const role = m.role as 'user' | 'assistant'
      if (role === 'user') {
        return { role, text: m.content, toolCalls: [], done: true }
      }
      return {
        role,
        text: m.content,
        toolCalls: m.tool_invocations.map(mapStoredToolCall),
        done: true,
        interrupted: m.finish_reason === 'interrupted',
        error: m.finish_reason === 'error' ? 'La respuesta falló.' : undefined,
      }
    })
}

function applyEvent(messages: UIMessage[], ev: ChatEvent): UIMessage[] {
  const next = [...messages]
  const last = next[next.length - 1]
  if (!last || last.role !== 'assistant') return next

  switch (ev.type) {
    case 'text_delta':
      next[next.length - 1] = { ...last, text: last.text + ev.text }
      break
    case 'tool_use': {
      const call: ToolCall = { id: ev.id, name: ev.name, status: 'running' }
      next[next.length - 1] = { ...last, toolCalls: [...last.toolCalls, call] }
      break
    }
    case 'tool_result': {
      next[next.length - 1] = {
        ...last,
        toolCalls: last.toolCalls.map((c) =>
          c.id === ev.tool_use_id ? { ...c, status: ev.is_error ? 'error' : 'success' } : c,
        ),
      }
      break
    }
    case 'done':
      next[next.length - 1] = {
        ...last,
        done: true,
        toolCalls: last.toolCalls.map((c) =>
          c.status === 'running' ? { ...c, status: 'success' } : c,
        ),
      }
      break
    case 'error':
      next[next.length - 1] = { ...last, done: true, error: ev.message }
      break
    case 'thinking_delta':
    case 'title_update':
      break
  }
  return next
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<UIMessage[]>([])
  const loadingConversations = ref(false)
  const loadingMessages = ref(false)
  const streaming = ref(false)
  const error = ref<string | null>(null)

  let abortController: AbortController | null = null

  const activeConversation = computed(
    () => conversations.value.find((c) => c.id === activeConversationId.value) ?? null,
  )

  function patchConversation(id: string, patch: Partial<Conversation>): void {
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx === -1) return
    const existing = conversations.value[idx]
    if (!existing) return
    conversations.value[idx] = { ...existing, ...patch }
  }

  function applyTitleUpdate(id: string, title: string): void {
    const conv = conversations.value.find((c) => c.id === id)
    if (!conv || conv.title_locked) return
    patchConversation(id, { title })
  }

  async function loadConversations(): Promise<void> {
    loadingConversations.value = true
    error.value = null
    try {
      conversations.value = await conversationService.list({ limit: 100 })
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loadingConversations.value = false
    }
  }

  async function loadConversation(id: string): Promise<void> {
    activeConversationId.value = id
    loadingMessages.value = true
    messages.value = []
    error.value = null
    try {
      const detail = await conversationService.get(id)
      messages.value = toUIMessages(detail.messages)
      const idx = conversations.value.findIndex((c) => c.id === id)
      if (idx === -1) conversations.value = [detail.conversation, ...conversations.value]
      else conversations.value[idx] = detail.conversation
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loadingMessages.value = false
    }
  }

  async function createConversation(title?: string): Promise<Conversation> {
    const conv = await conversationService.create(title)
    conversations.value = [conv, ...conversations.value]
    activeConversationId.value = conv.id
    messages.value = []
    return conv
  }

  async function renameConversation(id: string, title: string): Promise<void> {
    const trimmed = title.trim()
    if (!trimmed) return
    const updated = await conversationService.rename(id, trimmed)
    patchConversation(id, updated)
  }

  function clearActive(): void {
    activeConversationId.value = null
    messages.value = []
  }

  async function sendMessage(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || streaming.value) return

    let convId = activeConversationId.value
    if (!convId) {
      const conv = await createConversation()
      convId = conv.id
    }
    const targetConvId = convId

    messages.value = [
      ...messages.value,
      { role: 'user', text: trimmed, toolCalls: [], done: true },
      { role: 'assistant', text: '', toolCalls: [], done: false },
    ]

    streaming.value = true
    error.value = null
    abortController = new AbortController()

    try {
      for await (const ev of agentService.stream(targetConvId, trimmed, abortController.signal)) {
        if (ev.type === 'title_update') {
          applyTitleUpdate(targetConvId, ev.title)
          continue
        }
        messages.value = applyEvent(messages.value, ev)
      }
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant' && !last.done) {
        messages.value = [...messages.value.slice(0, -1), { ...last, done: true }]
      }
      const convIdx = conversations.value.findIndex((c) => c.id === targetConvId)
      const existing = convIdx !== -1 ? conversations.value[convIdx] : undefined
      if (existing) {
        const updated = { ...existing, updated_at: new Date().toISOString() }
        conversations.value = [updated, ...conversations.value.filter((_, i) => i !== convIdx)]
      }
    } catch (e) {
      const err = e as Error
      if (err.name === 'AbortError') {
        const last = messages.value[messages.value.length - 1]
        if (last && last.role === 'assistant') {
          messages.value = [
            ...messages.value.slice(0, -1),
            { ...last, done: true, interrupted: true },
          ]
        }
      } else {
        error.value = err.message
        messages.value = applyEvent(messages.value, { type: 'error', message: err.message })
      }
    } finally {
      streaming.value = false
      abortController = null
    }
  }

  function stopStream(): void {
    abortController?.abort()
  }

  return {
    conversations,
    activeConversationId,
    activeConversation,
    messages,
    loadingConversations,
    loadingMessages,
    streaming,
    error,
    loadConversations,
    loadConversation,
    createConversation,
    renameConversation,
    clearActive,
    sendMessage,
    stopStream,
  }
})
