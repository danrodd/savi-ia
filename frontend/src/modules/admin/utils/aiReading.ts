/**
 * Lectura de PDF con IA: conteo de páginas en el navegador, costo estimado
 * y etiquetas. Sin Vue: se testean solas.
 *
 * El conteo corre en el navegador para mostrar el costo ANTES de subir, sin
 * mandar el archivo a ningún lado. `pdf-lib` se carga con import dinámico:
 * solo lo baja quien abre el diálogo de subida y elige un PDF.
 */
import type { AiReadingSettings, CompanyDocument, ReadingMethod } from '../types'

export function isPdf(file: File): boolean {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

/** Páginas del PDF, o `null` si no se pudo leer (el backend decidirá). */
export async function countPdfPages(file: File): Promise<number | null> {
  try {
    const { PDFDocument } = await import('pdf-lib')
    const bytes = await file.arrayBuffer()
    // Los cifrados sin contraseña se pueden contar igual; el backend los
    // rechaza si no los puede abrir.
    const document = await PDFDocument.load(bytes, {
      ignoreEncryption: true,
      updateMetadata: false,
    })
    return document.getPageCount()
  } catch {
    return null
  }
}

/** Si un PDF subido ahora se va a leer con IA. */
export function willReadWithAi(settings: AiReadingSettings | null): boolean {
  return (
    !!settings && settings.ai_reading_enabled && settings.available && !settings.consent_required
  )
}

/** Si activar la lectura necesita que el administrador acepte el aviso. */
export function needsConsent(settings: AiReadingSettings | null): boolean {
  if (!settings?.available || !settings.provider) return false
  return settings.consent_required || settings.consent_provider !== settings.provider
}

/** Costo estimado en USD, o `null` si no hay precio o páginas. */
export function estimateCost(
  pages: number | null,
  settings: AiReadingSettings | null,
): number | null {
  if (pages === null || !willReadWithAi(settings)) return null
  const perPage = settings?.estimated_usd_per_page
  if (perPage === null || perPage === undefined) return null
  return pages * perPage
}

/**
 * USD con los decimales que el monto necesita: los costos por documento son
 * de centavos o fracciones, y "US$0,00" no le dice nada a nadie.
 */
export function formatUsd(amount: number): string {
  if (amount > 0 && amount < 0.01) return '< US$0,01'
  return `US$${amount.toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** Monto aproximado: "~US$0,26", o "< US$0,01" si no llega a un centavo. */
export function approxUsd(amount: number): string {
  const formatted = formatUsd(amount)
  return formatted.startsWith('<') ? formatted : `~${formatted}`
}

export const READING_LABELS: Record<ReadingMethod, string> = {
  ai: 'IA',
  text: 'Texto',
  mixed: 'Mixto',
}

/** Detalle para el `title` de la etiqueta "Leído con". */
export function readingDetail(
  document: Pick<
    CompanyDocument,
    'reading_method' | 'ai_page_count' | 'page_count' | 'ai_cost_usd'
  >,
): string | null {
  if (document.reading_method === null) return null
  if (document.reading_method === 'text') return 'Leído con el texto digital del PDF.'
  const pages = document.page_count ?? document.ai_page_count
  let detail = `${document.ai_page_count} de ${pages} páginas leídas con IA`
  if (document.ai_cost_usd !== null) detail += ` · ${formatUsd(document.ai_cost_usd)}`
  return `${detail}.`
}

/** Texto del avance mientras se procesa. */
export function progressLabel(
  document: Pick<CompanyDocument, 'progress_done' | 'progress_total' | 'progress_stage'>,
): string | null {
  if (document.progress_done === null || document.progress_total === null) return null
  if (document.progress_stage === 'reading') {
    return `Leyendo con IA: página ${document.progress_done} de ${document.progress_total}`
  }
  return null
}

/** "Leer con IA" solo tiene sentido en un PDF que no se está procesando. */
export function canReadWithAi(document: Pick<CompanyDocument, 'media_type' | 'status'>): boolean {
  return (
    document.media_type === 'application/pdf' &&
    document.status !== 'pending' &&
    document.status !== 'processing'
  )
}

/** Línea de cada PDF en el diálogo de subida. `undefined` = contando. */
export function pdfReadingHint(
  pages: number | null | undefined,
  settings: AiReadingSettings | null,
): string {
  if (pages === undefined) return 'Contando páginas…'
  const count = pages === null ? '' : `${pages} ${pages === 1 ? 'página' : 'páginas'} · `
  if (!willReadWithAi(settings)) return `${count}se leerá solo el texto digital`
  const cost = estimateCost(pages, settings)
  return `${count}se leerá con IA${cost === null ? '' : ` · ${approxUsd(cost)}`}`
}

/**
 * Resumen del lote: "3 PDF · 45 páginas · ~US$0,03". `null` si no hay PDF o
 * todavía se están contando.
 */
export function batchSummary(
  pages: readonly (number | null | undefined)[],
  settings: AiReadingSettings | null,
): string | null {
  if (pages.length === 0 || pages.some((p) => p === undefined)) return null
  const known = pages.filter((p): p is number => typeof p === 'number')
  const total = known.reduce((sum, p) => sum + p, 0)
  let summary = `${pages.length} PDF · ${total} ${total === 1 ? 'página' : 'páginas'}`
  const cost = estimateCost(total, settings)
  if (cost !== null) summary += ` · ${approxUsd(cost)} con IA`
  return summary
}
