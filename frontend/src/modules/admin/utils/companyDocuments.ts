/**
 * Reglas y etiquetas de los documentos de la empresa, sin Vue: se testean solas.
 *
 * La validación del cliente es solo UX. El backend vuelve a validar todo
 * (tipo por contenido, tamaño, coherencia de permisos, bases existentes).
 */
import { z } from 'zod'

import { MODULE_LABELS, type ModuleCode } from '@/modules/permisos'
import type {
  CompanyDocument,
  DocumentPermissions,
  DocumentStatus,
  DocumentVisibility,
  ExclusionReason,
} from '../types'

// Mismo límite que el backend: un PDF de fotos del celular pesa 1-5 MB por página.
export const MAX_FILE_MB = 60
export const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md', '.markdown'] as const
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(',')

export const permissionsSchema = z
  .object({
    visibility: z.enum(['all', 'modules', 'admins']),
    modules: z.array(z.string()),
    all_databases: z.boolean(),
    database_ids: z.array(z.string()),
  })
  .superRefine((value, ctx) => {
    if (value.visibility === 'modules' && value.modules.length === 0) {
      ctx.addIssue({ code: 'custom', path: ['modules'], message: 'Elegí al menos un módulo.' })
    }
    if (!value.all_databases && value.database_ids.length === 0) {
      ctx.addIssue({ code: 'custom', path: ['database_ids'], message: 'Elegí al menos una base.' })
    }
  })

/** Primer mensaje de error, o `null` si los permisos son coherentes. */
export function validatePermissions(permissions: DocumentPermissions): string | null {
  const result = permissionsSchema.safeParse(permissions)
  return result.success ? null : (result.error.issues[0]?.message ?? 'Permisos inválidos.')
}

/** Lo que se envía: sin módulos fuera de "por módulos" ni bases con alcance total. */
export function normalizePermissions(permissions: DocumentPermissions): DocumentPermissions {
  return {
    visibility: permissions.visibility,
    modules: permissions.visibility === 'modules' ? [...permissions.modules] : [],
    all_databases: permissions.all_databases,
    database_ids: permissions.all_databases ? [] : [...permissions.database_ids],
  }
}

export function defaultPermissions(): DocumentPermissions {
  return { visibility: 'all', modules: [], all_databases: true, database_ids: [] }
}

export function permissionsOf(document: DocumentPermissions): DocumentPermissions {
  return {
    visibility: document.visibility,
    modules: [...document.modules],
    all_databases: document.all_databases,
    database_ids: [...document.database_ids],
  }
}

/**
 * `true` si el cambio puede dejar sin acceso a alguien que hoy lo tiene.
 * Se usa para pedir confirmación: las citas históricas de esas personas
 * pasan a mostrarse como no disponibles.
 */
export function narrowsAccess(before: DocumentPermissions, after: DocumentPermissions): boolean {
  const rank: Record<DocumentVisibility, number> = { all: 0, modules: 1, admins: 2 }
  if (rank[after.visibility] > rank[before.visibility]) return true
  if (before.visibility === 'modules' && after.visibility === 'modules') {
    if (before.modules.some((m) => !after.modules.includes(m))) return true
  }
  if (before.all_databases && !after.all_databases) return true
  if (!before.all_databases && !after.all_databases) {
    return before.database_ids.some((id) => !after.database_ids.includes(id))
  }
  return false
}

export interface FileCheck {
  ok: boolean
  reason?: string
}

/** Chequeo previo del navegador: extensión y tamaño. */
export function checkFile(file: File): FileCheck {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return { ok: false, reason: 'Solo se aceptan PDF, TXT y Markdown.' }
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return { ok: false, reason: `Supera el límite de ${MAX_FILE_MB} MB.` }
  }
  return { ok: true }
}

export function titleFromFilename(filename: string): string {
  return filename.replace(/\.[^.]+$/, '')
}

type StatusTone = 'muted' | 'info' | 'ok' | 'warn' | 'danger'

// "Sin texto" y "Error" son dos jergas para lo mismo desde el punto de vista de
// quien sube el documento: no se pudo leer. La causa va en la pista de la fila.
export const STATUS_LABELS: Record<DocumentStatus, { label: string; tone: StatusTone }> = {
  pending: { label: 'En cola', tone: 'muted' },
  processing: { label: 'Procesando…', tone: 'info' },
  ready: { label: 'Listo', tone: 'ok' },
  no_text: { label: 'No se pudo leer', tone: 'warn' },
  failed: { label: 'No se pudo leer', tone: 'danger' },
}

/** Motivos (`status_code`) en los que la lectura con IA falló por el proveedor. */
const AI_PROVIDER_FAILURE_CODES = new Set(['ai_failed', 'ai_no_credits', 'ai_daily_quota'])

/** `true` si el documento no se leyó porque el proveedor de IA no respondió. */
export function isAiProviderFailure(
  document: Pick<CompanyDocument, 'status' | 'status_code'>,
): boolean {
  return (
    (document.status === 'no_text' || document.status === 'failed') &&
    document.status_code !== null &&
    AI_PROVIDER_FAILURE_CODES.has(document.status_code)
  )
}

// Una línea que dice qué hacer, no qué pasó por dentro. El mensaje largo del
// backend queda como tooltip para soporte.
const FAILURE_HINTS: Record<string, string> = {
  ai_failed: 'Revisá el proveedor de IA.',
  ai_no_credits: 'Revisá el proveedor de IA.',
  ai_daily_quota: 'Revisá el proveedor de IA.',
  ai_unreadable: 'La IA no pudo leer las páginas. Probá con un escaneo más nítido.',
  pdf_encrypted: 'Quitale la contraseña al PDF y subilo de nuevo.',
  pdf_unreadable: 'El PDF parece dañado. Probá subirlo de nuevo.',
  encoding_unsupported: 'Guardalo como texto UTF-8 y subilo de nuevo.',
  too_many_pages: 'Es demasiado largo. Dividilo en partes más chicas.',
  too_many_chunks: 'Es demasiado largo. Dividilo en partes más chicas.',
  index_limit_reached: 'Se llenó el espacio de búsqueda. Eliminá documentos que ya no uses.',
}

export interface DocumentStatusView {
  label: string
  tone: StatusTone
  /** Qué hacer si no se pudo leer; `null` si no hace falta. */
  hint: string | null
}

export function documentStatusView(
  document: Pick<CompanyDocument, 'status' | 'status_code' | 'reading_method'>,
  context: { aiReadingAvailable: boolean },
): DocumentStatusView {
  const base = STATUS_LABELS[document.status]
  if (document.status === 'ready') {
    const withAi = document.reading_method === 'ai' || document.reading_method === 'mixed'
    return { ...base, label: withAi ? 'Listo (leído con IA)' : base.label, hint: null }
  }
  if (document.status !== 'no_text' && document.status !== 'failed') {
    return { ...base, hint: null }
  }
  const known = document.status_code ? FAILURE_HINTS[document.status_code] : undefined
  if (known) return { ...base, hint: known }
  if (document.status === 'no_text') {
    return {
      ...base,
      hint: context.aiReadingAvailable
        ? 'Probá «Leer con IA» desde el menú ⋯.'
        : 'Probá activar la lectura con IA en Configuración.',
    }
  }
  return { ...base, hint: 'Probá reprocesarlo desde el menú ⋯.' }
}

export function isInProgress(status: DocumentStatus): boolean {
  return status === 'pending' || status === 'processing'
}

export function moduleLabel(code: string): string {
  return MODULE_LABELS[code as ModuleCode] ?? code
}

export function visibilityLabel(document: Pick<CompanyDocument, 'visibility' | 'modules'>): string {
  if (document.visibility === 'all') return 'Toda la empresa'
  if (document.visibility === 'admins') return 'Solo administradores'
  return document.modules.map(moduleLabel).join(', ') || 'Por módulos'
}

export const EXCLUSION_LABELS: Record<ExclusionReason, string> = {
  visibility_admins: 'Solo administradores',
  visibility_modules: 'No tiene los módulos requeridos',
  database_scope: 'No aplica en esta base',
  not_available: 'No disponible',
}

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB'] as const

/** "1,5 KB", "6,7 MB": con coma decimal, como se lee en español. */
export function formatBytes(bytes: number): string {
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024
    unit++
  }
  const digits = unit === 0 || value >= 10 ? 0 : 1
  const text = value.toLocaleString('es-CO', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  return `${text} ${BYTE_UNITS[unit]}`
}

/** "77 documentos · 6,7 MB": lo que importa del espacio usado. */
export function usageSummary(usage: { total: number; bytes_stored: number }): string {
  const documents = usage.total === 1 ? '1 documento' : `${usage.total} documentos`
  return `${documents} · ${formatBytes(usage.bytes_stored)}`
}
