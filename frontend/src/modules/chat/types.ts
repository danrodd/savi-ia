export interface Conversation {
  id: string
  user_id: string | null
  title: string
  created_at: string
  updated_at: string
}

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool'

export interface StoredMessage {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  created_at: string
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
