/**
 * Tipos del módulo de administración. Reflejan 1:1 las responses del
 * backend (`/admin/erp-databases` y `/erp-databases/available`).
 */

export interface ErpDatabase {
  id: string
  code: string
  name: string
  host: string
  port: number
  database: string
  username: string
  statement_timeout_ms: number
  is_default: boolean
  is_active: boolean
  credentials_unreadable: boolean
  is_usable: boolean
  last_connection_ok_at: string | null
  created_at: string
  updated_at: string
}

export interface SaveErpDatabaseRequest {
  code: string
  name: string
  host: string
  port: number
  database: string
  username: string
  password?: string
  statement_timeout_ms: number
}

export interface ConnectionTestResult {
  ok: boolean
  detail: string
  razon_social: string | null
  missing_tables: string[]
  /** El usuario del ERP es superusuario de Postgres: se muestra advertencia. */
  is_superuser: boolean
}

export interface AvailableErpDatabase {
  id: string
  code: string
  name: string
}

export interface ErpDatabaseFormValues {
  code: string
  name: string
  host: string
  port: number
  database: string
  username: string
  password: string
  statement_timeout_ms: number
}

export interface ExportedErpDatabasesFile {
  version: number
  exported_at: string
  count: number
  payload: string
}

export interface ImportRowResult {
  code: string
  status: 'created' | 'updated' | 'failed'
  detail: string | null
}

export interface ImportErpDatabasesResult {
  rows: ImportRowResult[]
}

export type LlmProviderKind = 'claude' | 'gemini' | 'openai'
export type LlmCredentialKind = 'api_key' | 'oauth_token' | 'local_session'

export interface ModelPricing {
  input: number
  output: number
  cache_read: number
  cache_write: number
}

export interface LlmProvider {
  provider: LlmProviderKind
  display_name: string
  implemented: boolean
  credential_kinds: LlmCredentialKind[]
  supports_model_listing: boolean
  configured: boolean
  credential_kind: LlmCredentialKind | null
  has_credential: boolean
  credentials_unreadable: boolean
  chat_model: string | null
  title_model: string | null
  pricing: Record<string, ModelPricing>
  is_active: boolean
  last_test_ok_at: string | null
}

export interface SaveLlmProviderRequest {
  credential_kind: LlmCredentialKind
  credential?: string
  chat_model: string
  title_model: string
  pricing?: Record<string, ModelPricing>
}

export interface ProviderModel {
  id: string
  display_name: string
  metadata?: Record<string, unknown>
}

export interface ProviderTestResponse {
  ok: boolean
  detail: string
  models: ProviderModel[]
}

// ── Conocimiento de la empresa (documentos propios) ─────────────────────

export type DocumentVisibility = 'all' | 'modules' | 'admins'
export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'no_text' | 'failed'

export interface CompanyDocument {
  id: string
  title: string
  original_filename: string
  media_type: string
  size_bytes: number
  version: number
  status: DocumentStatus
  status_code: string | null
  status_message: string | null
  page_count: number | null
  chunk_count: number
  char_count: number
  embedding_model: string | null
  visibility: DocumentVisibility
  modules: string[]
  all_databases: boolean
  database_ids: string[]
  uploaded_by_login: string
  processed_at: string | null
  created_at: string
  updated_at: string
}

/** Permisos de un documento: quién lo ve y en qué bases aplica. */
export interface DocumentPermissions {
  visibility: DocumentVisibility
  modules: string[]
  all_databases: boolean
  database_ids: string[]
}

export interface UpdateCompanyDocumentRequest extends Partial<DocumentPermissions> {
  title?: string
}

export interface CompanyDocumentUsage {
  total: number
  by_status: Record<DocumentStatus, number>
  chunks: number
  chunk_limit: number
  bytes_stored: number
  estimated_index_memory_bytes: number
  embedding_model: string
}

export type ExclusionReason =
  | 'visibility_admins'
  | 'visibility_modules'
  | 'database_scope'
  | 'not_available'

export interface SearchTestResult {
  context: { login: string; has_access: boolean; modules: string[]; is_admin: boolean }
  results: {
    document_id: string
    title: string
    pages: string | null
    heading: string | null
    snippet: string
    vector_score: number
    bm25_score: number
    rrf_score: number
  }[]
  excluded_documents: { document_id: string; title: string; reason: ExclusionReason }[]
}
