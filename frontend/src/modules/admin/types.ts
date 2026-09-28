import type { Component } from 'vue'

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
  /** El proveedor informa el costo facturado del turno: no hay precios que cargar. */
  reports_cost: boolean
  configured: boolean
  credential_kind: LlmCredentialKind | null
  has_credential: boolean
  credentials_unreadable: boolean
  chat_model: string | null
  title_model: string | null
  /** Modelo para leer documentos. `null` = usa el modelo de chat. */
  document_model: string | null
  pricing: Record<string, ModelPricing>
  is_active: boolean
  last_test_ok_at: string | null
}

export interface SaveLlmProviderRequest {
  credential_kind: LlmCredentialKind
  credential?: string
  chat_model: string
  title_model: string
  /** Omitido = conservar el guardado; vacío = usar el modelo de chat. */
  document_model?: string
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
export type ReadingMethod = 'text' | 'ai' | 'mixed'
export type DocumentProgressStage = 'reading' | 'indexing'

/** Lectura de PDF con IA: interruptor y con qué se lee. */
export interface AiReadingSettings {
  ai_reading_enabled: boolean
  /** Hay un proveedor activo que puede leer documentos. */
  available: boolean
  provider: string | null
  provider_name: string | null
  model: string | null
  /** Claude por sesión o token OAuth: la lectura gasta el límite de la suscripción. */
  uses_subscription: boolean
  /** `null` si el modelo no tiene precios cargados. */
  estimated_usd_per_page: number | null
  unavailable_reason: string | null
  privacy_notice: string
  updated_by_login: string | null
  updated_at: string | null
  /** Activada, pero nadie aceptó el envío al proveedor activo: en pausa. */
  consent_required: boolean
  /** Proveedor al que se aceptó enviar los PDF, quién y cuándo. */
  consent_provider: string | null
  consent_provider_name: string | null
  consent_by_login: string | null
  consent_at: string | null
}

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
  /**
   * Avance del procesamiento en curso. `null` salvo mientras se procesa:
   * el backend lo mantiene en memoria, no en la base.
   */
  progress_done: number | null
  progress_total: number | null
  /** `reading`: leyendo con IA; `indexing`: indexando. */
  progress_stage: DocumentProgressStage | null
  char_count: number
  embedding_model: string | null
  /** Solo PDF. `null` hasta procesarlo. */
  reading_method: ReadingMethod | null
  ai_page_count: number
  ai_cost_usd: number | null
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

/** Cupo de cargas por usuario y por hora (subir, reemplazar, leer sitios). */
export interface UploadLimit {
  /** `null`: se usa el valor por defecto del servidor. */
  upload_limit_per_hour: number | null
  default: number
  maximum: number
  effective: number
  updated_by_login: string | null
  updated_at: string | null
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

// ── Sitios web (Fase 5) ─────────────────────────────────────────────────────
// Reflejan `/admin/company-web-sources`. Cada página importada es un
// documento más del conocimiento, con su link en las citas.

export type WebSourceMode = 'page' | 'site'
export type RefreshFrequency = 'manual' | 'daily' | 'weekly'
export type WebSourceStatus = 'pending' | 'crawling' | 'ready' | 'failed'
export type WebPageStatus = 'imported' | 'unchanged' | 'skipped' | 'failed' | 'removed'

export interface WebSource extends DocumentPermissions {
  id: string
  url: string
  mode: WebSourceMode
  title: string
  refresh: RefreshFrequency
  max_pages: number
  excluded_sections: string[]
  status: WebSourceStatus
  status_code: string | null
  status_message: string | null
  page_count: number
  skipped_count: number
  last_crawl_started_at: string | null
  last_crawl_finished_at: string | null
  next_refresh_at: string | null
  created_by_login: string
  created_at: string
}

export interface WebPage {
  document_id: string
  url: string
  title: string
  status: WebPageStatus
  status_detail: string | null
  last_fetched_at: string | null
  last_changed_at: string | null
}

export interface WebSourceDetail extends WebSource {
  pages: WebPage[]
}

export interface WebSourcePreview {
  url: string
  title: string
  sample: string
  words: number
  page_count: number
  truncated: boolean
  used_sitemap: boolean
  /** Páginas por sección del sitemap, para excluir las que no aportan. */
  sections: Record<string, number>
  warnings: string[]
}

export interface PreviewWebSourceRequest {
  url: string
  mode: WebSourceMode
  max_pages: number
  excluded_sections: string[]
}

export interface CreateWebSourceRequest extends PreviewWebSourceRequest, DocumentPermissions {
  title?: string
  refresh: RefreshFrequency
}

export interface UpdateWebSourceRequest extends Partial<DocumentPermissions> {
  title?: string
  refresh?: RefreshFrequency
  max_pages?: number
  excluded_sections?: string[]
}

/** Acción del menú de tres puntos de una fila. */
export interface RowAction<Id extends string = string> {
  id: Id
  label: string
  icon: Component
  danger?: boolean
  disabled?: boolean
  /** Separador antes de esta acción. */
  divider?: boolean
}
