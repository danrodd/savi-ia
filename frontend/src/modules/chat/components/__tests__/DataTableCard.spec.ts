import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { formatPreviewCell, rowCountLabel } from '../../utils/dataTables'

const serviceMock = vi.hoisted(() => ({ preview: vi.fn(), export: vi.fn() }))
vi.mock('../../services/resultSetService', () => ({ resultSetService: serviceMock }))
const downloadMock = vi.hoisted(() => vi.fn())
vi.mock('@/lib/download', () => ({ triggerDownload: downloadMock }))

import DataTableCard from '../DataTableCard.vue'

const TABLE = {
  id: 'rs-1',
  title: 'Ventas por producto · producto contiene LLANTAS0183',
  total_rows: 214,
  total_is_lower_bound: false,
}

function preview(rows: number) {
  return {
    id: 'rs-1',
    title: TABLE.title,
    columns: [
      { key: 'cliente', label: 'Cliente', kind: 'text' },
      { key: 'celular', label: 'Celular', kind: 'text' },
      { key: 'unidades', label: 'Unidades', kind: 'number' },
    ],
    rows: Array.from({ length: rows }, (_, i) => [`Cliente ${i + 1}`, '3001234567', 1000 + i]),
    total_rows: 214,
    total_is_lower_bound: false,
    created_at: '2026-11-11T21:30:00Z',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:x')
  globalThis.URL.revokeObjectURL = vi.fn()
})

describe('DataTableCard', () => {
  it('muestra una vista previa corta y dice cuántas filas hay en total', async () => {
    serviceMock.preview.mockResolvedValue(preview(30))

    const wrapper = mount(DataTableCard, { props: { table: TABLE } })
    await flushPromises()

    expect(wrapper.findAll('tbody tr')).toHaveLength(8)
    expect(wrapper.text()).toContain('Mostrando 8 de 214 filas')
    expect(wrapper.text()).toContain('Para ver todas las filas, use Exportar.')

    await wrapper.find('.data-card__more').trigger('click')
    expect(wrapper.findAll('tbody tr')).toHaveLength(30)
  })

  it('Exportar pide el archivo al servidor y lo descarga', async () => {
    serviceMock.preview.mockResolvedValue(preview(3))
    serviceMock.export.mockResolvedValue(new Blob(['x']))
    const wrapper = mount(DataTableCard, { props: { table: TABLE }, attachTo: document.body })
    await flushPromises()

    await (wrapper.vm as unknown as { exportAs: (f: string) => Promise<void> }).exportAs('xlsx')

    expect(serviceMock.export).toHaveBeenCalledWith('rs-1', 'xlsx')
    expect(downloadMock).toHaveBeenCalledWith(
      'blob:x',
      'Ventas por producto · producto contiene LLANTAS0183.xlsx',
    )
    wrapper.unmount()
  })

  it('si los datos vencieron, lo dice', async () => {
    const { HttpRequestError } = await import('@/lib/HttpClient')
    serviceMock.preview.mockRejectedValue(new HttpRequestError('no existe', 404))

    const wrapper = mount(DataTableCard, { props: { table: TABLE } })
    await flushPromises()

    expect(wrapper.text()).toContain('ya no están disponibles')
  })
})

describe('dataTables utils', () => {
  it('arma la leyenda de filas', () => {
    expect(rowCountLabel(8, 214, false)).toBe('Mostrando 8 de 214 filas')
    expect(rowCountLabel(3, 3, false)).toBe('3 filas')
    expect(rowCountLabel(30, 10000, true)).toBe('Mostrando 30 de más de 10.000 filas')
  })

  it('formatea números y fechas de la vista previa', () => {
    expect(formatPreviewCell(1234567.5, 'number')).toBe('1.234.567,5')
    expect(formatPreviewCell('2026-11-11', 'date')).toBe('11/11/2026')
    expect(formatPreviewCell(null, 'text')).toBe('—')
  })
})
