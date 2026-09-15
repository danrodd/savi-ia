import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { HttpRequestError } from '@/lib/HttpClient'
import { type AvailableErpDatabase, erpDatabaseService } from '@/modules/admin'
import { agentService } from '../services/agentService'
import { conversationService } from '../services/conversationService'
import type {
  ChatEvent,
  Conversation,
  MessageVersion,
  SendChatBody,
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

function storedToUI(m: StoredMessage): UIMessage {
  const role = m.role as 'user' | 'assistant'
  if (role === 'user') {
    return { tempId: m.id, id: m.id, role, text: m.content, toolCalls: [], done: true }
  }
  return {
    tempId: m.id,
    id: m.id,
    role,
    text: m.content,
    toolCalls: m.tool_invocations.map(mapStoredToolCall),
    done: true,
    interrupted: m.finish_reason === 'interrupted',
    error: m.finish_reason === 'error' ? 'La respuesta falló.' : undefined,
    sources: m.sources ?? [],
  }
}

let placeholderSeq = 0
function makeTempId(): string {
  placeholderSeq++
  return `pl-${Date.now().toString(36)}-${placeholderSeq}`
}

function placeholderUser(text: string): UIMessage {
  return {
    tempId: makeTempId(),
    id: null,
    role: 'user',
    text,
    toolCalls: [],
    done: true,
  }
}

function placeholderAssistant(): UIMessage {
  return {
    tempId: makeTempId(),
    id: null,
    role: 'assistant',
    text: '',
    toolCalls: [],
    done: false,
  }
}

function toUIMessages(stored: StoredMessage[]): UIMessage[] {
  return stored
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.superseded_at === null)
    .map(storedToUI)
}

function storedToVersion(m: StoredMessage): MessageVersion {
  return {
    id: m.id,
    text: m.content,
    created_at: m.created_at,
    toolCalls: m.tool_invocations.map(mapStoredToolCall),
    interrupted: m.finish_reason === 'interrupted',
  }
}

function buildVersionChains(all: StoredMessage[]): Record<string, MessageVersion[]> {
  const byId = new Map(all.map((m) => [m.id, m]))
  const predecessorOf = new Map<string, string>()
  for (const m of all) {
    if (m.superseded_by_id) predecessorOf.set(m.superseded_by_id, m.id)
  }
  const chains: Record<string, MessageVersion[]> = {}
  for (const m of all) {
    if (m.superseded_at !== null) continue
    if (m.role !== 'user' && m.role !== 'assistant') continue
    const chain: StoredMessage[] = [m]
    let currentId: string = m.id
    while (true) {
      const predId = predecessorOf.get(currentId)
      if (!predId) break
      const pred = byId.get(predId)
      if (!pred) break
      chain.unshift(pred)
      currentId = pred.id
    }
    if (chain.length > 1) chains[m.id] = chain.map(storedToVersion)
  }
  return chains
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
    case 'sources':
      next[next.length - 1] = { ...last, sources: ev.sources }
      break
    case 'thinking_delta':
    case 'title_update':
    case 'superseded':
      break
  }
  return next
}

function isDatabaseUnavailable(e: unknown): boolean {
  return e instanceof HttpRequestError && e.body.errorCode === 'erp_database_unavailable'
}

function isLlmProviderUnavailable(e: unknown): boolean {
  return e instanceof HttpRequestError && e.body.errorCode === 'llm_provider_unavailable'
}

function findLastIndex<T>(arr: T[], predicate: (item: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i] !== undefined && predicate(arr[i] as T)) return i
  }
  return -1
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const activeConversationId = ref<string | null>(null)
  const messages = ref<UIMessage[]>([])
  const versionsByActiveId = ref<Record<string, MessageVersion[]>>({})
  const loadingConversations = ref(false)
  const loadingMessages = ref(false)
  const streaming = ref(false)
  const error = ref<string | null>(null)
  const llmProviderUnavailable = ref(false)

  // Bases del ERP a las que el usuario tiene acceso. La de una conversación
  // se fija al crearla y no cambia; la selección solo aplica a la próxima.
  const availableDatabases = ref<AvailableErpDatabase[]>([])
  const availableDatabasesLoaded = ref(false)
  const selectedDatabaseId = ref<string | null>(null)
  const unavailableDatabaseIds = ref<Set<string>>(new Set())

  let abortController: AbortController | null = null

  const activeConversation = computed(
    () => conversations.value.find((c) => c.id === activeConversationId.value) ?? null,
  )

  const databaseNameById = computed(
    () => new Map(availableDatabases.value.map((db) => [db.id, db.name])),
  )

  function isDatabaseUsable(id: string | null): boolean {
    if (!id || !availableDatabasesLoaded.value) return true
    return databaseNameById.value.has(id) && !unavailableDatabaseIds.value.has(id)
  }

  const activeDatabaseUnavailable = computed(
    () =>
      activeConversation.value !== null &&
      !isDatabaseUsable(activeConversation.value.erp_database_id),
  )

  // Con un solo cliente el nombre en cada conversación es ruido; se muestra
  // en cuanto hay más de una base o alguna conversación quedó sin la suya.
  const showsDatabaseContext = computed(
    () =>
      availableDatabases.value.length > 1 ||
      conversations.value.some((c) => !isDatabaseUsable(c.erp_database_id)),
  )

  const lastUserIndex = computed(() => findLastIndex(messages.value, (m) => m.role === 'user'))

  const lastAssistantIndex = computed(() =>
    findLastIndex(messages.value, (m) => m.role === 'assistant' && m.done),
  )

  const canRegenerate = computed(() => {
    if (streaming.value) return false
    const idx = lastAssistantIndex.value
    if (idx === -1) return false
    const after = messages.value.slice(idx + 1)
    return after.every((m) => m.role !== 'user')
  })

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

  function applySuperseded(ids: string[]): void {
    if (ids.length === 0) return
    const removed = new Set(ids)
    messages.value = messages.value.filter((m) => !(m.id !== null && removed.has(m.id)))
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
    versionsByActiveId.value = {}
    error.value = null
    try {
      const detail = await conversationService.getWithVersions(id)
      messages.value = toUIMessages(detail.messages)
      versionsByActiveId.value = buildVersionChains(detail.messages)
      const idx = conversations.value.findIndex((c) => c.id === id)
      if (idx === -1) conversations.value = [detail.conversation, ...conversations.value]
      else conversations.value[idx] = detail.conversation
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loadingMessages.value = false
    }
  }

  /**
   * Hidrata IDs reales en los placeholders locales sin reemplazar el array.
   * Preserva los tempIds (claves de Vue) → evita unmount/remount y parpadeo.
   *
   * Race condition resuelta: el writer del mensaje del asistente corre en
   * `asyncio.create_task` con sessionmaker independiente del request — el
   * SSE puede haber emitido `done` pero el INSERT todavía no haber hecho
   * commit. Si en ese instante hacemos `GET /conversations/{id}`, el
   * backend devuelve menos mensajes de los que tenemos localmente. NO
   * debemos pisar el array — esperamos al próximo tick con backoff.
   *
   * Reglas:
   * - fresh.length === local.length → patch IDs en-place.
   * - fresh.length > local.length    → usar `fresh` (raro pero seguro).
   * - fresh.length < local.length    → NO pisar; reintentar con backoff.
   */
  async function hydrateActiveMessages(): Promise<void> {
    const id = activeConversationId.value
    if (!id) return
    const MAX_ATTEMPTS = 5
    const BACKOFF_MS = [200, 400, 800, 1500, 2500] as const

    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      // Si el usuario cambió de conversación mientras esperábamos, abortamos.
      if (activeConversationId.value !== id) return
      try {
        const detail = await conversationService.getWithVersions(id)
        const fresh = toUIMessages(detail.messages)
        versionsByActiveId.value = buildVersionChains(detail.messages)

        if (fresh.length === messages.value.length) {
          // Caso normal: el backend ya tiene todo, hidratamos IDs en-place.
          for (let i = 0; i < fresh.length; i++) {
            const local = messages.value[i]
            const remote = fresh[i]
            if (!local || !remote) continue
            if (local.role !== remote.role) {
              messages.value = fresh
              return
            }
            if (local.id === null) local.id = remote.id
          }
          return
        }

        if (fresh.length > messages.value.length) {
          // Backend tiene MÁS que el store: improbable salvo edits cruzados.
          // Confiamos en el backend.
          messages.value = fresh
          return
        }

        // fresh.length < local.length: writer en vuelo. NO pisar.
        // Reintento con backoff hasta MAX_ATTEMPTS.
        const wait = BACKOFF_MS[attempt] ?? 2500
        await new Promise((resolve) => setTimeout(resolve, wait))
      } catch {
        // silencioso — el flujo principal ya manejó el error
        return
      }
    }
    // Si tras todos los reintentos el backend sigue corto, no tocamos el
    // array local: el mensaje queda con id=null (no se podrá editar ni
    // versionar hasta el próximo refetch). Es el menor mal posible.
  }

  async function loadAvailableDatabases(): Promise<void> {
    try {
      availableDatabases.value = await erpDatabaseService.available()
      availableDatabasesLoaded.value = true
      const selected = selectedDatabaseId.value
      if (selected && !databaseNameById.value.has(selected)) selectedDatabaseId.value = null
    } catch {
      // Sin la lista el chat sigue funcionando contra la base de inicio de sesión.
    }
  }

  function markDatabaseUnavailable(id: string): void {
    unavailableDatabaseIds.value = new Set([...unavailableDatabaseIds.value, id])
  }

  async function createConversation(title?: string): Promise<Conversation> {
    const conv = await conversationService.create({
      title,
      erpDatabaseId: selectedDatabaseId.value,
    })
    conversations.value = [conv, ...conversations.value]
    activeConversationId.value = conv.id
    messages.value = []
    versionsByActiveId.value = {}
    return conv
  }

  async function renameConversation(id: string, title: string): Promise<void> {
    const trimmed = title.trim()
    if (!trimmed) return
    const updated = await conversationService.rename(id, trimmed)
    patchConversation(id, updated)
  }

  /**
   * Optimistic delete: oculta la conversación del sidebar inmediatamente,
   * llama al DELETE, revierte si el backend devuelve 4xx (404 cuando nunca
   * existió). El 204 — incluso si llega tras un reintento — confirma.
   * Si la conversación eliminada era la activa, la limpia y devuelve true
   * para que la vista navegue a home.
   */
  async function deleteConversation(id: string): Promise<{ wasActive: boolean }> {
    const idx = conversations.value.findIndex((c) => c.id === id)
    if (idx === -1) return { wasActive: false }
    const snapshot = conversations.value[idx]
    if (!snapshot) return { wasActive: false }

    const wasActive = activeConversationId.value === id
    conversations.value = conversations.value.filter((c) => c.id !== id)
    if (wasActive) clearActive()

    try {
      await conversationService.delete(id)
      return { wasActive }
    } catch (e) {
      // Revertir: re-insertar en la misma posición; si era la activa,
      // la vista decide si reabrir o quedarse en home.
      conversations.value = [
        ...conversations.value.slice(0, idx),
        snapshot,
        ...conversations.value.slice(idx),
      ]
      error.value = (e as Error).message
      throw e
    }
  }

  function clearActive(): void {
    activeConversationId.value = null
    messages.value = []
    versionsByActiveId.value = {}
  }

  function bumpConversationToTop(convId: string): void {
    const convIdx = conversations.value.findIndex((c) => c.id === convId)
    const existing = convIdx !== -1 ? conversations.value[convIdx] : undefined
    if (!existing) return
    const updated = { ...existing, updated_at: new Date().toISOString() }
    conversations.value = [updated, ...conversations.value.filter((_, i) => i !== convIdx)]
  }

  async function runChatTurn(targetConvId: string, body: SendChatBody): Promise<void> {
    streaming.value = true
    error.value = null
    abortController = new AbortController()

    try {
      for await (const ev of agentService.stream(body, abortController.signal)) {
        if (ev.type === 'title_update') {
          applyTitleUpdate(targetConvId, ev.title)
          continue
        }
        if (ev.type === 'superseded') {
          applySuperseded(ev.message_ids)
          continue
        }
        messages.value = applyEvent(messages.value, ev)
      }
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant' && !last.done) {
        messages.value = [...messages.value.slice(0, -1), { ...last, done: true }]
      }
      bumpConversationToTop(targetConvId)
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
      } else if (isDatabaseUnavailable(err)) {
        // El backend corta antes de abrir el stream: no se persistió nada,
        // así que se quitan los placeholders del turno.
        messages.value = messages.value.filter((m) => m.id !== null)
        const conv = conversations.value.find((c) => c.id === targetConvId)
        if (conv?.erp_database_id) markDatabaseUnavailable(conv.erp_database_id)
        void loadAvailableDatabases()
      } else if (isLlmProviderUnavailable(err)) {
        // La respuesta se rechaza antes de abrir el SSE, por lo que ningún
        // placeholder del turno debe quedar visible en el hilo local.
        llmProviderUnavailable.value = true
        messages.value = messages.value.filter((m) => m.id !== null)
      } else {
        error.value = err.message
        messages.value = applyEvent(messages.value, { type: 'error', message: err.message })
      }
    } finally {
      streaming.value = false
      abortController = null
    }
    // Hidratar IDs y cadenas en background — no bloquea la aparición de los
    // botones de copiar/editar/regenerar, que dependen de !streaming.
    void hydrateActiveMessages()
  }

  async function sendMessage(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || streaming.value || llmProviderUnavailable.value) return

    let convId = activeConversationId.value
    if (!convId) {
      try {
        const conv = await createConversation()
        convId = conv.id
      } catch (e) {
        error.value = (e as Error).message || 'No se pudo crear la conversación.'
        if (isDatabaseUnavailable(e)) void loadAvailableDatabases()
        if (isLlmProviderUnavailable(e)) llmProviderUnavailable.value = true
        return
      }
    }
    const targetConvId = convId

    messages.value.push(placeholderUser(trimmed), placeholderAssistant())

    await runChatTurn(targetConvId, {
      conversation_id: targetConvId,
      action: 'send',
      message: trimmed,
    })
  }

  async function editLastUserMessage(text: string): Promise<void> {
    const trimmed = text.trim()
    const convId = activeConversationId.value
    if (!trimmed || !convId || streaming.value) return
    const lastIdx = lastUserIndex.value
    if (lastIdx === -1) return

    // Reemplazo optimista in-place: quita el user viejo (y assistant si seguía)
    // y los sustituye por el user nuevo + placeholder. El usuario ve la misma
    // transición que un send normal (no se renderiza nada por unos ms).
    messages.value.splice(
      lastIdx,
      messages.value.length - lastIdx,
      placeholderUser(trimmed),
      placeholderAssistant(),
    )

    await runChatTurn(convId, {
      conversation_id: convId,
      action: 'edit_last',
      message: trimmed,
    })
  }

  async function regenerateLastAssistant(): Promise<void> {
    const convId = activeConversationId.value
    if (!convId || streaming.value || !canRegenerate.value) return
    const lastIdx = lastAssistantIndex.value
    if (lastIdx === -1) return

    // Reemplazo optimista in-place del assistant viejo por placeholder.
    messages.value.splice(lastIdx, messages.value.length - lastIdx, placeholderAssistant())

    await runChatTurn(convId, {
      conversation_id: convId,
      action: 'regenerate',
    })
  }

  function stopStream(): void {
    abortController?.abort()
  }

  return {
    conversations,
    activeConversationId,
    activeConversation,
    messages,
    versionsByActiveId,
    loadingConversations,
    loadingMessages,
    streaming,
    error,
    llmProviderUnavailable,
    lastUserIndex,
    lastAssistantIndex,
    canRegenerate,
    availableDatabases,
    selectedDatabaseId,
    databaseNameById,
    activeDatabaseUnavailable,
    showsDatabaseContext,
    isDatabaseUsable,
    loadAvailableDatabases,
    loadConversations,
    loadConversation,
    createConversation,
    renameConversation,
    deleteConversation,
    clearActive,
    sendMessage,
    editLastUserMessage,
    regenerateLastAssistant,
    stopStream,
  }
})
