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

export const MAX_FILE_MB = 20
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
      ctx.addIssue({ code: 'custom', path: ['modules'], message: 'Elige al menos un módulo.' })
    }
    if (!value.all_databases && value.database_ids.length === 0) {
      ctx.addIssue({ code: 'custom', path: ['database_ids'], message: 'Elige al menos una base.' })
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

export function permissionsOf(document: CompanyDocument): DocumentPermissions {
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

export const STATUS_LABELS: Record<
  DocumentStatus,
  { label: string; tone: 'muted' | 'info' | 'ok' | 'warn' | 'danger' }
> = {
  pending: { label: 'En cola', tone: 'muted' },
  processing: { label: 'Procesando…', tone: 'info' },
  ready: { label: 'Listo', tone: 'ok' },
  no_text: { label: 'Sin texto', tone: 'warn' },
  failed: { label: 'Error', tone: 'danger' },
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

export function formatBytes(bytes: number): string {
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024
    unit++
  }
  const digits = unit === 0 || value >= 10 ? 0 : 1
  return `${value.toFixed(digits)} ${BYTE_UNITS[unit]}`
}
