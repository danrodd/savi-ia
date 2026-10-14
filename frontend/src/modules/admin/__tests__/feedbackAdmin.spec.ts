import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FeedbackItem, FeedbackPage, FeedbackSummary } from '../types'
import {
  barPercent,
  buildFeedbackQuery,
  emptyFeedbackFilters,
  FEEDBACK_EXPORT_HEADERS,
  feedbackExportRows,
  shortQuestion,
  topReasonLabel,
} from '../utils/feedback'

const serviceMock = vi.hoisted(() => ({ list: vi.fn(), summary: vi.fn(), exportCsv: vi.fn() }))
vi.mock('../services/feedbackService', () => ({ feedbackAdminService: serviceMock }))

import { useFeedbackStore } from '../stores/feedbackStore'

function item(over: Partial<FeedbackItem> = {}): FeedbackItem {
  return {
    id: 'f1',
    rating: 'down',
    reason: 'incompleta',
    comment: 'Faltó',
    created_at: '2026-10-13T10:00:00Z',
    updated_at: '2026-10-13T10:00:00Z',
    user_id: 7,
    user_login: 'ANA',
    user_name: 'Ana',
    conversation_id: 'c1',
    message_id: 'm1',
    question: '¿Cuánto vendimos?',
    answer: '10 millones',
    provider: 'claude',
    model: 'sonnet',
    cost_usd: 0.01,
    tools: ['consultar_datos'],
    database_code: 'NORTE',
    ...over,
  }
}

const EMPTY_SUMMARY: FeedbackSummary = {
  total: 0,
  up: 0,
  down: 0,
  positive_pct: null,
  daily: [],
  top_reasons: [],
  by_model: [],
}

describe('buildFeedbackQuery', () => {
  it('sin filtros no manda nada', () => {
    expect(buildFeedbackQuery(emptyFeedbackFilters())).toEqual({})
  })

  it('traduce los filtros a los nombres del backend', () => {
    const query = buildFeedbackQuery(
      {
        rating: 'down',
        reason: 'muy_lenta',
        from: '2026-10-01',
        to: '2026-10-13',
        model: ' sonnet ',
        user: 'ana',
        text: 'iva',
      },
      { limit: 25, offset: 50 },
    )

    expect(query).toEqual({
      rating: 'down',
      reason: 'muy_lenta',
      from: '2026-10-01',
      to: '2026-10-13',
      model: 'sonnet',
      user: 'ana',
      q: 'iva',
      limit: 25,
      offset: 50,
    })
  })

  it('no manda motivo con 👍 (no existe)', () => {
    const query = buildFeedbackQuery({ ...emptyFeedbackFilters(), rating: 'up', reason: 'otra' })

    expect(query).toEqual({ rating: 'up' })
  })
})

describe('helpers', () => {
  it('barPercent da una barra mínima visible y 0 sin datos', () => {
    expect(barPercent(0, 10)).toBe(0)
    expect(barPercent(1, 100)).toBe(4)
    expect(barPercent(10, 10)).toBe(100)
    expect(barPercent(5, 0)).toBe(0)
  })

  it('shortQuestion colapsa espacios y recorta', () => {
    expect(shortQuestion('  hola\n  mundo ')).toBe('hola mundo')
    expect(shortQuestion('x'.repeat(200), 10)).toBe(`${'x'.repeat(9)}…`)
    expect(shortQuestion(null)).toBe('—')
  })

  it('topReasonLabel usa el texto amigable', () => {
    expect(topReasonLabel([{ reason: 'dato_incorrecto', count: 3 }])).toBe(
      'El dato es incorrecto (3)',
    )
    expect(topReasonLabel([])).toBe('—')
  })

  it('las filas del Excel siguen las columnas del CSV', () => {
    const rows = feedbackExportRows([item()])

    expect(rows[0]).toEqual(FEEDBACK_EXPORT_HEADERS)
    expect(rows[1]).toHaveLength(FEEDBACK_EXPORT_HEADERS.length)
    expect(rows[1]?.[3]).toBe('No me sirvió')
    expect(rows[1]?.[4]).toBe('Está incompleta')
    expect(rows[1]?.[11]).toBe('consultar_datos')
  })
})

describe('feedbackStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const page: FeedbackPage = { items: [item()], total: 60, limit: 25, offset: 0 }
    serviceMock.list.mockResolvedValue(page)
    serviceMock.summary.mockResolvedValue(EMPTY_SUMMARY)
  })

  it('carga lista y resumen con los mismos filtros', async () => {
    const store = useFeedbackStore()

    await store.applyFilters({ ...emptyFeedbackFilters(), rating: 'down' })

    expect(serviceMock.list).toHaveBeenCalledWith({ rating: 'down', limit: 25, offset: 0 })
    expect(serviceMock.summary).toHaveBeenCalledWith({ rating: 'down' })
    expect(store.items).toHaveLength(1)
    expect(store.pageCount).toBe(3)
  })

  it('cambiar de página pide el offset correspondiente', async () => {
    const store = useFeedbackStore()
    await store.load()

    await store.goToPage(2)

    expect(serviceMock.list).toHaveBeenLastCalledWith({ limit: 25, offset: 50 })
  })

  it('filtrar vuelve a la primera página', async () => {
    const store = useFeedbackStore()
    await store.load()
    await store.goToPage(1)

    await store.applyFilters({ ...emptyFeedbackFilters(), text: 'iva' })

    expect(store.page).toBe(0)
    expect(serviceMock.list).toHaveBeenLastCalledWith({ q: 'iva', limit: 25, offset: 0 })
  })

  it('muestra el error del backend', async () => {
    serviceMock.list.mockRejectedValue(new Error('Se requiere rol administrador.'))
    const store = useFeedbackStore()

    await store.load()

    expect(store.error).toBe('Se requiere rol administrador.')
    expect(store.loading).toBe(false)
  })
})
