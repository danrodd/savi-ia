/**
 * Etiquetas y reglas de los sitios web del conocimiento, sin Vue.
 */
import type { RefreshFrequency, WebPageStatus, WebSource, WebSourceStatus } from '../types'

type Tone = 'muted' | 'info' | 'ok' | 'warn' | 'danger'

export const WEB_STATUS_LABELS: Record<WebSourceStatus, { label: string; tone: Tone }> = {
  pending: { label: 'En cola', tone: 'muted' },
  crawling: { label: 'Leyendo el sitio…', tone: 'info' },
  ready: { label: 'Listo', tone: 'ok' },
  failed: { label: 'Error', tone: 'danger' },
}

export const PAGE_STATUS_LABELS: Record<WebPageStatus, { label: string; tone: Tone }> = {
  imported: { label: 'Importada', tone: 'ok' },
  unchanged: { label: 'Sin cambios', tone: 'ok' },
  skipped: { label: 'Omitida', tone: 'muted' },
  failed: { label: 'Error', tone: 'danger' },
  removed: { label: 'Dada de baja', tone: 'warn' },
}

export const REFRESH_LABELS: Record<RefreshFrequency, string> = {
  manual: 'Solo manual',
  daily: 'Diario',
  weekly: 'Semanal',
}

export function isWebInProgress(status: WebSourceStatus): boolean {
  return status === 'pending' || status === 'crawling'
}

/** "www.surandina.com.co" en vez de la URL entera. */
export function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

export function pagesSummary(
  source: Pick<WebSource, 'mode' | 'page_count' | 'skipped_count'>,
): string {
  if (source.mode === 'page') return 'Una página'
  const pages = source.page_count === 1 ? '1 página' : `${source.page_count} páginas`
  return source.skipped_count > 0 ? `${pages} · ${source.skipped_count} omitidas` : pages
}

/** Quien escribe "www.sitio.com" espera que funcione: se completa con https. */
export function normalizeUrlInput(raw: string): string {
  const value = raw.trim()
  if (!value) return ''
  return /^https?:\/\//i.test(value) ? value : `https://${value}`
}

export function isValidUrlInput(raw: string): boolean {
  try {
    const url = new URL(normalizeUrlInput(raw))
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.hostname.includes('.')
  } catch {
    return false
  }
}

/**
 * Nombre legible de una sección del sitemap: "wp-sitemap-posts-page-1.xml"
 * pasa a "posts page 1" y "product-sitemap.xml" a "product".
 */
export function sectionLabel(section: string): string {
  if (section === 'links') return 'Enlaces del sitio'
  const name = section
    .replace(/\.xml(\.gz)?$/i, '')
    .replace(/^wp-sitemap-?/i, '')
    .replace(/[-_]?sitemap[-_]?/gi, ' ')
    .replace(/[-_]+/g, ' ')
    .trim()
  return name || section
}

/**
 * Páginas que se leerán al excluir secciones. `pageCount` es lo que el
 * backend ya seleccionó (sin carrito, duplicados ni el tope); los conteos
 * por sección son crudos, así que al restar es un aproximado: nunca menos
 * de la página raíz.
 */
export function estimatePages(
  pageCount: number,
  sections: Record<string, number>,
  excluded: string[],
): number {
  const removed = excluded.reduce((sum, name) => sum + (sections[name] ?? 0), 0)
  return Math.max(1, pageCount - removed)
}
