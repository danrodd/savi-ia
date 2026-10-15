import { describe, expect, it } from 'vitest'
import type { CompanyDocument } from '../types'
import { documentStatusView, isAiProviderFailure, usageSummary } from '../utils/companyDocuments'

type StatusFields = Pick<CompanyDocument, 'status' | 'status_code' | 'reading_method'>

const doc = (overrides: Partial<StatusFields>): StatusFields => ({
  status: 'ready',
  status_code: null,
  reading_method: null,
  ...overrides,
})

const ctx = { aiReadingAvailable: false }

describe('documentStatusView', () => {
  it('"Leído con Texto" pasa a un simple "Listo"', () => {
    const view = documentStatusView(doc({ reading_method: 'text' }), ctx)

    expect(view.label).toBe('Listo')
    expect(view.hint).toBeNull()
  })

  it('un documento leído con IA lo aclara entre paréntesis', () => {
    expect(documentStatusView(doc({ reading_method: 'ai' }), ctx).label).toBe(
      'Listo (leído con IA)',
    )
    expect(documentStatusView(doc({ reading_method: 'mixed' }), ctx).label).toBe(
      'Listo (leído con IA)',
    )
  })

  it('"Sin texto" y los errores se muestran como "No se pudo leer"', () => {
    expect(documentStatusView(doc({ status: 'no_text' }), ctx).label).toBe('No se pudo leer')
    expect(documentStatusView(doc({ status: 'failed' }), ctx).label).toBe('No se pudo leer')
  })

  it('un fallo del proveedor de IA manda a revisar el proveedor', () => {
    const view = documentStatusView(doc({ status: 'no_text', status_code: 'ai_failed' }), ctx)

    expect(view.hint).toBe('Revise el proveedor de IA.')
  })

  it('un PDF escaneado sugiere activar la lectura con IA si todavía no está activa', () => {
    const view = documentStatusView(doc({ status: 'no_text' }), { aiReadingAvailable: false })

    expect(view.hint).toBe('Pruebe activar la lectura con IA en Configuración.')
  })

  it('si la lectura con IA ya está disponible, sugiere usarla', () => {
    const view = documentStatusView(doc({ status: 'no_text' }), { aiReadingAvailable: true })

    expect(view.hint).toContain('Leer con IA')
  })

  it('un PDF con contraseña dice qué hacer', () => {
    const view = documentStatusView(doc({ status: 'failed', status_code: 'pdf_encrypted' }), ctx)

    expect(view.hint).toBe('Quítele la contraseña al PDF y súbalo de nuevo.')
  })

  it('las pistas usan voseo', () => {
    const hints = [
      documentStatusView(doc({ status: 'failed', status_code: 'pdf_unreadable' }), ctx).hint,
      documentStatusView(doc({ status: 'failed', status_code: 'too_many_pages' }), ctx).hint,
      documentStatusView(doc({ status: 'failed' }), ctx).hint,
    ].join(' ')

    expect(hints).not.toMatch(/Prueba |Quita |Revisa |Divide /)
  })
})

describe('isAiProviderFailure', () => {
  it('reconoce los tres motivos del proveedor', () => {
    for (const status_code of ['ai_failed', 'ai_no_credits', 'ai_daily_quota']) {
      expect(isAiProviderFailure({ status: 'no_text', status_code })).toBe(true)
    }
  })

  it('no confunde un PDF cifrado ni un documento listo', () => {
    expect(isAiProviderFailure({ status: 'failed', status_code: 'pdf_encrypted' })).toBe(false)
    expect(isAiProviderFailure({ status: 'ready', status_code: 'ai_failed' })).toBe(false)
  })
})

describe('usageSummary', () => {
  it('resume documentos y espacio, sin hablar de fragmentos', () => {
    const text = usageSummary({ total: 77, bytes_stored: 6.7 * 1024 * 1024 })

    expect(text).toBe('77 documentos · 6,7 MB')
    expect(text).not.toMatch(/fragmentos/)
  })

  it('usa la coma decimal y el singular', () => {
    expect(usageSummary({ total: 1, bytes_stored: 1.5 * 1024 * 1024 })).toBe('1 documento · 1,5 MB')
  })
})
