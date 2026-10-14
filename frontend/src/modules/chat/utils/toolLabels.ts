/**
 * Textos para mostrar al usuario cuando el asistente usa una herramienta. La
 * spec del backend (sección 6) prohíbe mostrar nombres técnicos de tools: acá
 * se traducen a lo que la persona entiende ("Consultando el ERP…").
 *
 * Cada herramienta pertenece a un "tipo" de consulta. El tipo es la clave de
 * agrupación (varias consultas al ERP se ven como una sola pastilla con ×N) y
 * decide el texto, que cambia según esté corriendo o terminado: en curso va en
 * gerundio con puntos suspensivos y al terminar pasa a pasado, sin contradecir
 * lo que se ve ("Consultó el ERP").
 */
import type { ToolCallStatus, ToolKind } from '../types'

const KIND_BY_TOOL: Record<string, ToolKind> = {
  consultar_datos: 'erp',
  consultar_libre: 'erp',
  info_empresa: 'company',
  consultar_conocimiento: 'knowledge',
}

/** Valores de `tipo` de `consultar_conocimiento` que leen documentos de la empresa. */
const DOCUMENT_KNOWLEDGE_TYPES = new Set(['documentos', 'documentos_disponibles'])

const RUNNING_LABELS: Record<ToolKind, string> = {
  erp: 'Consultando el ERP…',
  documents: 'Buscando en los documentos de la empresa…',
  knowledge: 'Buscando en el conocimiento del ERP…',
  company: 'Revisando los datos de la empresa…',
  other: 'Trabajando en tu consulta…',
}

const DONE_LABELS: Record<ToolKind, string> = {
  erp: 'Consultó el ERP',
  documents: 'Consultó los documentos',
  knowledge: 'Consultó el conocimiento del ERP',
  company: 'Revisó los datos de la empresa',
  other: 'Listo',
}

const ERROR_LABELS: Record<ToolKind, string> = {
  erp: 'No se pudo consultar el ERP',
  documents: 'No se pudo consultar los documentos',
  knowledge: 'No se pudo consultar el conocimiento del ERP',
  company: 'No se pudieron revisar los datos de la empresa',
  other: 'Algo no salió bien',
}

function bareName(name: string): string {
  return name.replace(/^mcp__.*?__/, '')
}

export function getToolKind(name: string, input?: Record<string, unknown>): ToolKind {
  const bare = bareName(name)
  const kind = KIND_BY_TOOL[bare] ?? 'other'
  if (kind !== 'knowledge') return kind
  const tipo = typeof input?.tipo === 'string' ? input.tipo.trim().toLowerCase() : ''
  return DOCUMENT_KNOWLEDGE_TYPES.has(tipo) ? 'documents' : 'knowledge'
}

export function getKindLabel(kind: ToolKind, status: ToolCallStatus): string {
  if (status === 'running') return RUNNING_LABELS[kind]
  if (status === 'error') return ERROR_LABELS[kind]
  return DONE_LABELS[kind]
}

export function getToolLabel(
  name: string,
  status: ToolCallStatus,
  input?: Record<string, unknown>,
): string {
  return getKindLabel(getToolKind(name, input), status)
}
