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
