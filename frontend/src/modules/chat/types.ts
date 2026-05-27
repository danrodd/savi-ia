export interface Conversation {
  id: string
  user_id: string | null
  title: string
  title_locked: boolean
  created_at: string
  updated_at: string
}

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool'
export type FinishReason = 'complete' | 'interrupted' | 'error' | 'truncated'

export interface TokenUsage {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

export type ToolInvocationStatus = 'running' | 'ok' | 'error'

export interface ToolInvocation {
  id: string
  name: string
  input: Record<string, unknown>
  status: ToolInvocationStatus
}

export interface StoredMessage {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  created_at: string
  finish_reason: FinishReason | null
  tool_invocations: ToolInvocation[]
  usage: TokenUsage | null
  cost_usd: string | null
  superseded_at: string | null
  superseded_by_id: string | null
}

export interface ConversationDetail {
  conversation: Conversation
  messages: StoredMessage[]
}

export type SendChatBody =
  | { conversation_id: string; action?: 'send'; message: string }
  | { conversation_id: string; action: 'edit_last'; message: string }
  | { conversation_id: string; action: 'regenerate' }

export type ChatEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'thinking_delta'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; is_error: boolean }
  | { type: 'superseded'; message_ids: string[] }
  | { type: 'title_update'; title: string }
  | {
      type: 'done'
      usage: Record<string, unknown> | null
      cost_usd: number | null
      finish_reason: string
    }
  | { type: 'error'; message: string }

export type ToolCallStatus = 'running' | 'success' | 'error'

export interface ToolCall {
  id: string
  name: string
  status: ToolCallStatus
}

export interface UIMessage {
  /** Estable durante todo el ciclo de vida del componente; usado como key de Vue. */
  tempId: string
  /** Real, asignado por el backend al persistir. null mientras es placeholder. */
  id: string | null
  role: 'user' | 'assistant'
  text: string
  toolCalls: ToolCall[]
  done: boolean
  interrupted?: boolean
  error?: string
}

export interface MessageVersion {
  id: string
  text: string
  created_at: string
  toolCalls: ToolCall[]
  interrupted: boolean
}
