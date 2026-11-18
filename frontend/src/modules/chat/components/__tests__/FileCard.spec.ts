import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fileKindLabel, fileSizeLabel } from '../../utils/files'

const getBlob = vi.hoisted(() => vi.fn())
vi.mock('@/lib/HttpClient', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/HttpClient')>()
  return {
    ...original,
    HttpClient: class {
      getBlob = getBlob
    },
  }
})
const downloadMock = vi.hoisted(() => vi.fn())
vi.mock('@/lib/download', () => ({ triggerDownload: downloadMock }))

import FileCard from '../FileCard.vue'

const FILE = {
  id: 'f-1',
  filename: 'Informe de llantas sin movimiento.pdf',
  media_type: 'application/pdf',
  size_bytes: 48_300,
}

beforeEach(() => {
  vi.clearAllMocks()
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:f')
  globalThis.URL.revokeObjectURL = vi.fn()
})

describe('FileCard', () => {
  it('muestra el tipo, el nombre y el tamaño, y descarga del servidor', async () => {
    getBlob.mockResolvedValue(new Blob(['%PDF']))
    const wrapper = mount(FileCard, { props: { file: FILE } })

    expect(wrapper.text()).toContain('PDF')
    expect(wrapper.text()).toContain('Informe de llantas sin movimiento.pdf')
    expect(wrapper.text()).toContain('47 KB')

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(getBlob).toHaveBeenCalledWith('/f-1')
    expect(downloadMock).toHaveBeenCalledWith('blob:f', FILE.filename)
  })

  it('si el archivo venció, lo dice', async () => {
    const { HttpRequestError } = await import('@/lib/HttpClient')
    getBlob.mockRejectedValue(new HttpRequestError('no', 404))
    const wrapper = mount(FileCard, { props: { file: FILE } })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('ya no está disponible')
  })
})

describe('files utils', () => {
  it('nombra el tipo y el tamaño', () => {
    expect(fileKindLabel('datos.xlsx')).toBe('Excel')
    expect(fileKindLabel('carta.docx')).toBe('Word')
    expect(fileSizeLabel(2_621_440)).toBe('2,5 MB')
  })
})
