export interface Conversation {
  id: string
  user_id: string | null
  erp_database_id: string | null
  title: string
  title_locked: boolean
  created_at: string
  updated_at: string
  /**
   * Mensajes activos (no superseded). Un backend anterior no lo manda: sin el
   * dato no se asume que la conversación está vacía.
   */
  message_count?: number
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

/** Documento de la empresa citado en una respuesta. */
export interface MessageSource {
  /** Primera referencia del documento en el texto (`D1`). */
  ref: string
  /** Todas las referencias de ese documento en el mensaje. */
  refs: string[]
  document_id: string
  version: number
  title: string
  /** `"3-4, 9"` en PDF; `null` en texto plano. */
  pages: string | null
  /** Página web de origen; `null` en documentos subidos. */
  url?: string | null
  /** Solo en el historial: calculado para quien consulta. */
  available?: boolean | null
  unavailable_reason?: 'deleted' | 'processing' | 'no_access' | null
}

/** Imagen adjunta tal como la devuelve el backend (solo mensajes del usuario). */
export interface ChatAttachment {
  id: string
  mime: string
  filename: string
  size_bytes: number
  width: number
  height: number
}

/**
 * Imagen adjunta lista para mostrar o reenviar. `previewUrl` es un object URL
 * local (la miniatura de la subida); si es `null`, los bytes se piden al
 * backend por `id`.
 */
export interface UIAttachment {
  id: string
  filename: string
  mime: string
  previewUrl: string | null
}

/** Calificación del usuario sobre una respuesta del asistente. */
export type FeedbackRating = 'up' | 'down'

/** Motivo de un 👎 (los valores son el contrato con el backend). */
export type FeedbackReason = 'dato_incorrecto' | 'no_entendio' | 'incompleta' | 'muy_lenta' | 'otra'

export interface MessageFeedback {
  rating: FeedbackRating
  reason: FeedbackReason | null
  comment: string | null
}

/** Lo que el usuario envía al calificar. `reason`/`comment` solo con `down`. */
export interface FeedbackInput {
  rating: FeedbackRating
  reason?: FeedbackReason | null
  comment?: string | null
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
  sources?: MessageSource[]
  attachments?: ChatAttachment[]
  /** Calificación propia. Un backend anterior no lo manda. */
  feedback?: MessageFeedback | null
}

export interface ConversationDetail {
  conversation: Conversation
  messages: StoredMessage[]
}

export type SendChatBody =
  | { conversation_id: string; action?: 'send'; message?: string; attachment_ids?: string[] }
  | { conversation_id: string; action: 'edit_last'; message?: string; attachment_ids?: string[] }
  | { conversation_id: string; action: 'regenerate' }

export type ChatEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'thinking_delta'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; is_error: boolean }
  | { type: 'superseded'; message_ids: string[] }
  | { type: 'title_update'; title: string }
  | { type: 'sources'; sources: MessageSource[] }
  | {
      type: 'done'
      usage: Record<string, unknown> | null
      cost_usd: number | null
      finish_reason: string
    }
  | { type: 'error'; message: string; code?: string | null }

export type ToolCallStatus = 'running' | 'success' | 'error'

/** Tipo de consulta que el usuario ve en la pastilla de progreso. */
export type ToolKind = 'erp' | 'documents' | 'knowledge' | 'company' | 'other'

export interface ToolCall {
  id: string
  name: string
  status: ToolCallStatus
  /** Argumentos de la llamada: solo sirven para elegir el texto amigable. */
  input?: Record<string, unknown>
}

/**
 * Agregación visual de tool calls con el mismo label público. La agrupación
 * usa el label (no el `name` técnico) para que tools distintas que mapean
 * al mismo texto amigable se fusionen en una sola pill con `×N`.
 */
export interface ToolCallGroup {
  /** Tipo de consulta (clave de agrupación). */
  kind: ToolKind
  label: string
  status: ToolCallStatus
  count: number
}

export interface UIMessage {
  /** Estable durante todo el ciclo de vida del componente; usado como key de Vue. */
  tempId: string
  /** Real, asignado por el backend al persistir. null mientras es placeholder. */
  id: string | null
  role: 'user' | 'assistant'
  text: string
  toolCalls: ToolCall[]
  /** ISO: cuándo se creó el mensaje. En los que se están generando es la hora local. */
  createdAt?: string
  done: boolean
  interrupted?: boolean
  error?: string
  sources?: MessageSource[]
  /** Calificación propia de la respuesta (`null`/ausente = sin calificar). */
  feedback?: MessageFeedback | null
  /** Imágenes adjuntas (solo mensajes del usuario). */
  attachments?: UIAttachment[]
}

export interface MessageVersion {
  id: string
  text: string
  created_at: string
  toolCalls: ToolCall[]
  interrupted: boolean
  attachments: UIAttachment[]
}
