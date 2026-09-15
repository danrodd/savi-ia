import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { installAuthBridge } from '@/lib/authBridge'
import { companyDocumentService } from '../services/companyDocumentService'
import { POLL_INTERVAL_MS, useCompanyDocumentStore } from '../stores/companyDocumentStore'
import type { CompanyDocument, CompanyDocumentUsage, DocumentPermissions } from '../types'
import {
  checkFile,
  formatBytes,
  narrowsAccess,
  normalizePermissions,
  validatePermissions,
  visibilityLabel,
} from '../utils/companyDocuments'

const perms = (overrides: Partial<DocumentPermissions> = {}): DocumentPermissions => ({
  visibility: 'all',
  modules: [],
  all_databases: true,
  database_ids: [],
  ...overrides,
})

describe('validatePermissions', () => {
  it('acepta toda la empresa en todas las bases', () => {
    expect(validatePermissions(perms())).toBeNull()
  })

  it('exige al menos un módulo con visibilidad por módulos', () => {
    expect(validatePermissions(perms({ visibility: 'modules' }))).toBe('Elige al menos un módulo.')
  })

  it('exige al menos una base cuando no aplica a todas', () => {
    expect(validatePermissions(perms({ all_databases: false }))).toBe('Elige al menos una base.')
  })
})

describe('normalizePermissions', () => {
  it('no envía módulos fuera de "por módulos" ni bases con alcance total', () => {
    const normalized = normalizePermissions(
      perms({
        visibility: 'admins',
        modules: ['VENTA'],
        all_databases: true,
        database_ids: ['b1'],
      }),
    )
    expect(normalized).toEqual(perms({ visibility: 'admins' }))
  })
})

describe('narrowsAccess', () => {
  it.each([
    ['toda la empresa → solo administradores', perms(), perms({ visibility: 'admins' }), true],
    [
      'toda la empresa → por módulos',
      perms(),
      perms({ visibility: 'modules', modules: ['VENTA'] }),
      true,
    ],
    [
      'quitar un módulo',
      perms({ visibility: 'modules', modules: ['VENTA', 'INVENTARIO'] }),
      perms({ visibility: 'modules', modules: ['VENTA'] }),
      true,
    ],
    [
      'agregar un módulo',
      perms({ visibility: 'modules', modules: ['VENTA'] }),
      perms({ visibility: 'modules', modules: ['VENTA', 'INVENTARIO'] }),
      false,
    ],
    [
      'todas las bases → algunas',
      perms(),
      perms({ all_databases: false, database_ids: ['b1'] }),
      true,
    ],
    [
      'quitar una base',
      perms({ all_databases: false, database_ids: ['b1', 'b2'] }),
      perms({ all_databases: false, database_ids: ['b1'] }),
      true,
    ],
    ['solo administradores → toda la empresa', perms({ visibility: 'admins' }), perms(), false],
    ['sin cambios', perms(), perms(), false],
  ])('%s', (_label, before, after, expected) => {
    expect(narrowsAccess(before, after)).toBe(expected)
  })
})

describe('checkFile', () => {
  it('rechaza extensiones no soportadas y archivos grandes', () => {
    expect(checkFile(new File(['x'], 'foto.png')).ok).toBe(false)
    const big = new File([new Uint8Array(21 * 1024 * 1024)], 'manual.pdf')
    expect(checkFile(big)).toEqual({ ok: false, reason: 'Supera el límite de 20 MB.' })
    expect(checkFile(new File(['# hola'], 'Manual.MD')).ok).toBe(true)
  })
})

describe('etiquetas', () => {
  it('formatea bytes y visibilidad legible', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(20 * 1024 * 1024)).toBe('20 MB')
    expect(visibilityLabel({ visibility: 'modules', modules: ['NÓMINA', 'CUENTACOBRAR'] })).toBe(
      'Nómina, Cuentas por cobrar',
    )
  })
})

describe('companyDocumentService.upload', () => {
  installAuthBridge({
    getAccessToken: () => 'token',
    refreshAccessToken: async () => '',
    clearSession: () => undefined,
    redirectToLogin: () => undefined,
    reloadPermisos: () => undefined,
  })

  afterEach(() => vi.restoreAllMocks())

  it('envía multipart sin fijar Content-Type y con módulos y bases repetidos', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ id: 'd1' }), { status: 201 }))

    await companyDocumentService.upload(
      new File(['hola'], 'politica.md'),
      'Política',
      perms({
        visibility: 'modules',
        modules: ['VENTA', 'INVENTARIO'],
        all_databases: false,
        database_ids: ['b1'],
      }),
    )

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
    expect(headers.Authorization).toBe('Bearer token')
    const form = init.body as FormData
    expect(form.getAll('modules')).toEqual(['VENTA', 'INVENTARIO'])
    expect(form.getAll('database_ids')).toEqual(['b1'])
    expect(form.get('all_databases')).toBe('false')
  })
})

describe('useCompanyDocumentStore polling', () => {
  const doc = (status: CompanyDocument['status']): CompanyDocument =>
    ({ id: 'd1', title: 'Manual', status }) as CompanyDocument
  const usage = { total: 1, chunks: 0, chunk_limit: 50000 } as CompanyDocumentUsage

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('refresca mientras hay documentos procesándose y se detiene al terminar', async () => {
    const list = vi
      .spyOn(companyDocumentService, 'list')
      .mockResolvedValueOnce([doc('processing')])
      .mockResolvedValueOnce([doc('ready')])
    vi.spyOn(companyDocumentService, 'usage').mockResolvedValue(usage)
    const store = useCompanyDocumentStore()

    store.startPolling()
    await store.load()
    expect(store.hasInProgress).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.documents[0]?.status).toBe('ready')

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('no sigue refrescando después de salir de la vista', async () => {
    const list = vi.spyOn(companyDocumentService, 'list').mockResolvedValue([doc('processing')])
    vi.spyOn(companyDocumentService, 'usage').mockResolvedValue(usage)
    const store = useCompanyDocumentStore()

    store.startPolling()
    await store.load()
    store.stopPolling()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(list).toHaveBeenCalledTimes(1)
  })
})
