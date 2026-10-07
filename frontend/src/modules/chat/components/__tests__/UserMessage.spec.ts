import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const downloadMock = vi.hoisted(() => vi.fn())

vi.mock('../../services/attachmentService', () => ({
  attachmentService: { upload: vi.fn(), download: downloadMock },
}))

import { clearAttachmentCache } from '../../lib/attachmentBlobCache'
import type { UIAttachment } from '../../types'
import UserMessage from '../UserMessage.vue'

function attachment(id: string, filename = `${id}.png`): UIAttachment {
  return { id, filename, mime: 'image/png', previewUrl: null }
}

function mountMessage(props: { text: string; attachments?: UIAttachment[] }) {
  return mount(UserMessage, {
    props: { messageId: 'm1', canEdit: true, versions: null, ...props },
    global: { stubs: { Dialog: true } },
  })
}

beforeEach(() => {
  clearAttachmentCache()
  vi.clearAllMocks()
  let n = 0
  URL.createObjectURL = vi.fn(() => `blob:img-${++n}`)
  URL.revokeObjectURL = vi.fn()
  downloadMock.mockResolvedValue(new Blob(['x'], { type: 'image/png' }))
})

describe('UserMessage · imágenes', () => {
  it('muestra las miniaturas traídas con autenticación, con el nombre como alt', async () => {
    const wrapper = mountMessage({
      text: 'mirá',
      attachments: [attachment('a', 'uno.png'), attachment('b', 'dos.png')],
    })
    await flushPromises()

    const imgs = wrapper.findAll('img')
    expect(imgs).toHaveLength(2)
    expect(imgs[0]?.attributes('alt')).toBe('uno.png')
    expect(imgs[0]?.attributes('src')).toMatch(/^blob:/)
    expect(downloadMock).toHaveBeenCalledTimes(2)
  })

  it('no vuelve a pedir una imagen que ya está en caché', async () => {
    const first = mountMessage({ text: 'a', attachments: [attachment('a')] })
    await flushPromises()
    first.unmount()

    const second = mountMessage({ text: 'a', attachments: [attachment('a')] })
    await flushPromises()

    expect(second.find('img').exists()).toBe(true)
    expect(downloadMock).toHaveBeenCalledTimes(1)
  })

  it('un mensaje solo con imágenes no deja una línea de texto vacía', async () => {
    const wrapper = mountMessage({ text: '', attachments: [attachment('a')] })
    await flushPromises()

    expect(wrapper.find('.bubble__text').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('un mensaje sin imágenes se ve como antes', () => {
    const wrapper = mountMessage({ text: 'hola' })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('.bubble__text').text()).toBe('hola')
  })

  it('al editar se pueden quitar imágenes y se envían las que quedan', async () => {
    const wrapper = mountMessage({
      text: 'hola',
      attachments: [attachment('a', 'uno.png'), attachment('b', 'dos.png')],
    })
    await flushPromises()

    await wrapper.find('.meta-btn:nth-child(2)').trigger('click')
    await wrapper.find('button[aria-label="Quitar imagen uno.png"]').trigger('click')
    await wrapper.find('.bubble__btn--primary').trigger('click')

    const [text, kept] = wrapper.emitted('edit')?.[0] as [string, UIAttachment[]]
    expect(text).toBe('hola')
    expect(kept.map((a) => a.id)).toEqual(['b'])
  })
})
