/**
 * Etiquetas y reglas de los sitios web del conocimiento, sin Vue.
 */
import type { RefreshFrequency, WebPageStatus, WebSource, WebSourceStatus } from '../types'

type Tone = 'muted' | 'info' | 'ok' | 'warn' | 'danger'

export const WEB_STATUS_LABELS: Record<WebSourceStatus, { label: string; tone: Tone }> = {
  pending: { label: 'En cola', tone: 'muted' },
  crawling: { label: 'Leyendo el sitio…', tone: 'info' },
  ready: { label: 'Listo', tone: 'ok' },
  failed: { label: 'No se pudo leer', tone: 'danger' },
}

export const PAGE_STATUS_LABELS: Record<WebPageStatus, { label: string; tone: Tone }> = {
  imported: { label: 'Leída', tone: 'ok' },
  unchanged: { label: 'Sin cambios', tone: 'ok' },
  skipped: { label: 'No se pudo leer', tone: 'muted' },
  failed: { label: 'No se pudo leer', tone: 'danger' },
  removed: { label: 'Ya no existe', tone: 'warn' },
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

/** "41 páginas leídas": lo que el sitio aportó. */
export function pagesReadLabel(source: Pick<WebSource, 'mode' | 'page_count'>): string {
  if (source.mode === 'page') return 'Una página'
  return source.page_count === 1 ? '1 página leída' : `${source.page_count} páginas leídas`
}

/** "4 no se pudieron leer", o `null` si todas se leyeron. */
export function pagesSkippedLabel(
  source: Pick<WebSource, 'mode' | 'skipped_count'>,
): string | null {
  if (source.mode === 'page' || source.skipped_count <= 0) return null
  return source.skipped_count === 1
    ? '1 no se pudo leer'
    : `${source.skipped_count} no se pudieron leer`
}

export function pagesSummary(
  source: Pick<WebSource, 'mode' | 'page_count' | 'skipped_count'>,
): string {
  const skipped = pagesSkippedLabel(source)
  return skipped ? `${pagesReadLabel(source)} · ${skipped}` : pagesReadLabel(source)
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

const SECTION_NAMES: Record<string, string> = {
  page: 'Páginas',
  post: 'Entradas del blog',
  product: 'Productos',
  category: 'Categorías del blog',
  post_tag: 'Etiquetas del blog',
  product_cat: 'Categorías de productos',
  product_tag: 'Etiquetas de productos',
  author: 'Autores',
  users: 'Autores',
  cartflows_step: 'Pasos de compra',
  sitemap: 'Mapa del sitio',
}

/**
 * Nombre legible de una sección del sitemap. Cubre WordPress
 * ("wp-sitemap-posts-page-1.xml" → "Páginas") y Yoast
 * ("product_cat-sitemap.xml" → "Categorías de productos"); lo desconocido
 * queda con el nombre del archivo limpio.
 */
export function sectionLabel(section: string): string {
  if (section === 'links') return 'Enlaces del sitio'
  let name = section.replace(/\.xml(\.gz)?$/i, '').toLowerCase()
  name = name.replace(/^wp-sitemap-?/, '').replace(/-?sitemap$/, '') || 'sitemap'
  const part = name.match(/-(\d+)$/)
  name = name.replace(/-(\d+)$/, '').replace(/^(posts|taxonomies)-/, '')
  const base = SECTION_NAMES[name] ?? capitalize(name.replace(/[-_]+/g, ' ').trim() || section)
  return part && Number(part[1]) > 1 ? `${base} (${part[1]})` : base
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
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
