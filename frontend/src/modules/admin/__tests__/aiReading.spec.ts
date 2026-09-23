import { PDFDocument } from 'pdf-lib'
import { describe, expect, it } from 'vitest'

import type { AiReadingSettings } from '../types'
import {
  approxUsd,
  batchSummary,
  canReadWithAi,
  countPdfPages,
  estimateCost,
  formatUsd,
  isPdf,
  needsConsent,
  pdfReadingHint,
  progressLabel,
  readingDetail,
  willReadWithAi,
} from '../utils/aiReading'

function settings(overrides: Partial<AiReadingSettings> = {}): AiReadingSettings {
  return {
    ai_reading_enabled: true,
    available: true,
    provider: 'openai',
    provider_name: 'OpenAI',
    model: 'gpt-6-luna',
    uses_subscription: false,
    estimated_usd_per_page: 0.0006,
    unavailable_reason: null,
    privacy_notice: 'Se envían a OpenAI.',
    updated_by_login: null,
    updated_at: null,
    consent_required: false,
    consent_provider: 'openai',
    consent_provider_name: 'OpenAI',
    consent_by_login: 'ADMIN',
    consent_at: '2026-09-23T18:00:00Z',
    ...overrides,
  }
}

async function pdfFile(pages: number, name = 'ficha.pdf'): Promise<File> {
  const document = await PDFDocument.create()
  for (let i = 0; i < pages; i++) document.addPage()
  const bytes = await document.save()
  return new File([bytes.slice().buffer], name, { type: 'application/pdf' })
}

describe('countPdfPages', () => {
  it('cuenta las páginas en el navegador', async () => {
    expect(await countPdfPages(await pdfFile(3))).toBe(3)
  })

  it('devuelve null si el archivo no es un PDF legible', async () => {
    const broken = new File(['no es un pdf'], 'roto.pdf', { type: 'application/pdf' })
    expect(await countPdfPages(broken)).toBeNull()
  })
})

describe('isPdf', () => {
  it('reconoce el PDF por tipo o por extensión', () => {
    expect(isPdf(new File(['x'], 'SCAN.PDF'))).toBe(true)
    expect(isPdf(new File(['x'], 'sin-extension', { type: 'application/pdf' }))).toBe(true)
    expect(isPdf(new File(['x'], 'manual.md'))).toBe(false)
  })
})

describe('needsConsent', () => {
  it('pide aceptar el aviso si nadie aceptó o si cambió el proveedor', () => {
    expect(needsConsent(settings())).toBe(false)
    expect(needsConsent(settings({ consent_provider: null }))).toBe(true)
    expect(needsConsent(settings({ provider: 'gemini' }))).toBe(true)
    expect(needsConsent(settings({ consent_required: true }))).toBe(true)
  })

  it('sin proveedor disponible no hay nada que aceptar', () => {
    expect(needsConsent(settings({ available: false, consent_provider: null }))).toBe(false)
    expect(needsConsent(null)).toBe(false)
  })
})

describe('estimado de costo', () => {
  it('solo lee con IA si está activa y disponible', () => {
    expect(willReadWithAi(settings())).toBe(true)
    expect(willReadWithAi(settings({ ai_reading_enabled: false }))).toBe(false)
    expect(willReadWithAi(settings({ available: false }))).toBe(false)
    expect(willReadWithAi(null)).toBe(false)
  })

  it('no lee con IA si el proveedor activo no fue aceptado', () => {
    expect(willReadWithAi(settings({ consent_required: true }))).toBe(false)
  })

  it('multiplica páginas por el precio por página', () => {
    expect(estimateCost(100, settings())).toBeCloseTo(0.06)
    expect(estimateCost(null, settings())).toBeNull()
    expect(estimateCost(10, settings({ estimated_usd_per_page: null }))).toBeNull()
    expect(estimateCost(10, settings({ ai_reading_enabled: false }))).toBeNull()
  })

  it('no muestra US$0,00 para montos de fracciones de centavo', () => {
    expect(formatUsd(0.004)).toBe('< US$0,01')
    expect(formatUsd(0)).toBe('US$0,00')
    expect(formatUsd(1.3)).toBe('US$1,30')
    expect(approxUsd(0.004)).toBe('< US$0,01')
    expect(approxUsd(0.26)).toBe('~US$0,26')
  })
})

describe('textos del diálogo de subida', () => {
  it('describe cada PDF según la configuración', () => {
    expect(pdfReadingHint(undefined, settings())).toBe('Contando páginas…')
    expect(pdfReadingHint(20, settings())).toBe('20 páginas · se leerá con IA · ~US$0,01')
    expect(pdfReadingHint(1, settings({ estimated_usd_per_page: null }))).toBe(
      '1 página · se leerá con IA',
    )
    expect(pdfReadingHint(20, settings({ ai_reading_enabled: false }))).toBe(
      '20 páginas · se leerá solo el texto digital',
    )
    expect(pdfReadingHint(null, settings({ available: false }))).toBe(
      'se leerá solo el texto digital',
    )
  })

  it('resume el lote cuando terminó de contar', () => {
    expect(batchSummary([12, undefined], settings())).toBeNull()
    expect(batchSummary([], settings())).toBeNull()
    expect(batchSummary([400, 30, null], settings())).toBe('3 PDF · 430 páginas · ~US$0,26 con IA')
    expect(batchSummary([5], settings({ ai_reading_enabled: false }))).toBe('1 PDF · 5 páginas')
  })
})

describe('estado del documento', () => {
  it('explica con qué se leyó', () => {
    const base = { page_count: 40, ai_page_count: 12, ai_cost_usd: 0.02 }
    expect(readingDetail({ ...base, reading_method: null })).toBeNull()
    expect(readingDetail({ ...base, reading_method: 'text' })).toBe(
      'Leído con el texto digital del PDF.',
    )
    expect(readingDetail({ ...base, reading_method: 'mixed' })).toBe(
      '12 de 40 páginas leídas con IA · US$0,02.',
    )
  })

  it('muestra el avance de la lectura con IA', () => {
    expect(progressLabel({ progress_done: 7, progress_total: 20, progress_stage: 'reading' })).toBe(
      'Leyendo con IA: página 7 de 20',
    )
    expect(
      progressLabel({ progress_done: 7, progress_total: 20, progress_stage: 'indexing' }),
    ).toBeNull()
    expect(
      progressLabel({ progress_done: null, progress_total: null, progress_stage: null }),
    ).toBeNull()
  })

  it('ofrece "Leer con IA" solo en PDF que no se están procesando', () => {
    expect(canReadWithAi({ media_type: 'application/pdf', status: 'no_text' })).toBe(true)
    expect(canReadWithAi({ media_type: 'application/pdf', status: 'processing' })).toBe(false)
    expect(canReadWithAi({ media_type: 'text/markdown', status: 'ready' })).toBe(false)
  })
})
