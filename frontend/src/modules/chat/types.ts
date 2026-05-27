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
}

export interface ConversationDetail {
  conversation: Conversation
  messages: StoredMessage[]
}

export type ChatEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'thinking_delta'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; is_error: boolean }
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
  role: 'user' | 'assistant'
  text: string
  toolCalls: ToolCall[]
  done: boolean
  interrupted?: boolean
  error?: string
}
