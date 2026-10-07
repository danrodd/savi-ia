import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const uploadMock = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }))

vi.mock('../../services/attachmentService', () => ({
  attachmentService: { upload: uploadMock, download: vi.fn() },
}))
vi.mock('@/lib/toast', () => ({ toast: toastMock }))

import Composer from '../Composer.vue'

function image(name = 'captura.png', type = 'image/png', size = 1024): File {
  const file = new File(['x'], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function uploaded(id: string, name = 'captura.png') {
  return { id, mime: 'image/png', filename: name, size_bytes: 1, width: 1, height: 1 }
}

function pasteEvent(files: File[]): { clipboardData: { files: File[] } } {
  return { clipboardData: { files } }
}

function dropOn(target: Element, files: File[]): void {
  const event = new Event('drop', { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'dataTransfer', { value: { files, types: ['Files'] } })
  target.dispatchEvent(event)
}

/** Promesa que se resuelve a mano, para sostener una subida "en curso". */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.clearAllMocks()
  let n = 0
  URL.createObjectURL = vi.fn(() => `blob:preview-${++n}`)
  URL.revokeObjectURL = vi.fn()
  uploadMock.mockImplementation(async (file: File) => uploaded(`id-${file.name}`, file.name))
})

/**
 * Cuando el backend rechaza un turno por límite de uso (429) o porque la
 * conversación ya tiene una respuesta en curso (409), el rechazo es temporal.
 * Perder lo que el usuario había escrito sería el peor castigo posible, así
 * que el texto vuelve al cuadro.
 */
describe('Composer', () => {
  it('devuelve el texto rechazado al cuadro', async () => {
    const wrapper = mount(Composer, { props: { streaming: false, restoreText: null } })

    await wrapper.setProps({ restoreText: '¿Cuántos empleados hay?' })

    expect(wrapper.find('textarea').element.value).toBe('¿Cuántos empleados hay?')
    expect(wrapper.emitted('restored')).toHaveLength(1)
  })

  it('no pisa lo que el usuario ya volvió a escribir', async () => {
    const wrapper = mount(Composer, { props: { streaming: false, restoreText: null } })
    await wrapper.find('textarea').setValue('otra pregunta')

    await wrapper.setProps({ restoreText: 'la vieja' })

    expect(wrapper.find('textarea').element.value).toBe('otra pregunta')
  })

  it('limpia el cuadro al enviar', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    await wrapper.find('textarea').setValue('hola')

    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('send')?.[0]).toEqual(['hola', []])
    expect(wrapper.find('textarea').element.value).toBe('')
  })
})

describe('Composer · imágenes adjuntas', () => {
  it('pegar una imagen la agrega y dispara la subida', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    const file = image()

    await wrapper.find('textarea').trigger('paste', pasteEvent([file]))
    await flushPromises()

    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(uploadMock.mock.calls[0]?.[0]).toBe(file)
    expect(wrapper.findAll('.chip')).toHaveLength(1)
  })

  it('pegar texto no agrega nada y no frena el pegado normal', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    const event = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'clipboardData', { value: { files: [] } })

    wrapper.find('textarea').element.dispatchEvent(event)
    await flushPromises()

    expect(event.defaultPrevented).toBe(false)
    expect(uploadMock).not.toHaveBeenCalled()
    expect(wrapper.findAll('.chip')).toHaveLength(0)
  })

  it('soltar imágenes sobre el contenedor las agrega', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    const zone = wrapper.element.parentElement as HTMLElement

    dropOn(zone, [image('a.png'), image('b.jpg', 'image/jpeg')])
    await flushPromises()

    expect(uploadMock).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.chip')).toHaveLength(2)
  })

  it('el selector de archivos agrega imágenes', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [image('foto.webp', 'image/webp')] })

    await input.trigger('change')
    await flushPromises()

    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('button[aria-label="Adjuntar imagen"]').exists()).toBe(true)
  })

  it('rechaza lo que pesa de más y lo que no es imagen, con un mensaje', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })

    await wrapper
      .find('textarea')
      .trigger('paste', pasteEvent([image('enorme.png', 'image/png', 6 * 1024 * 1024)]))
    expect(toastMock.error).toHaveBeenLastCalledWith('“enorme.png” pesa más de 5 MB.')

    dropOn(wrapper.element.parentElement as HTMLElement, [image('nota.pdf', 'application/pdf')])
    expect(toastMock.error).toHaveBeenLastCalledWith(
      '“nota.pdf” no es una imagen compatible. Usá PNG, JPG, WEBP o GIF.',
    )
    expect(uploadMock).not.toHaveBeenCalled()
  })

  it('no admite más de 4 imágenes por mensaje', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    const files = ['1', '2', '3', '4', '5'].map((n) => image(`${n}.png`))

    dropOn(wrapper.element.parentElement as HTMLElement, files)
    await flushPromises()

    expect(wrapper.findAll('.chip')).toHaveLength(4)
    expect(toastMock.error).toHaveBeenCalledWith('Podés adjuntar hasta 4 imágenes por mensaje.')
  })

  it('no deja enviar mientras una imagen se está subiendo', async () => {
    const pending = deferred<ReturnType<typeof uploaded>>()
    uploadMock.mockReturnValueOnce(pending.promise)
    const wrapper = mount(Composer, { props: { streaming: false } })

    await wrapper.find('textarea').setValue('mirá esto')
    await wrapper.find('textarea').trigger('paste', pasteEvent([image()]))
    const send = wrapper.find('button[aria-label="Enviar"]')
    expect(send.attributes('disabled')).toBeDefined()

    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('send')).toBeUndefined()

    pending.resolve(uploaded('id-1'))
    await flushPromises()
    expect(wrapper.find('button[aria-label="Enviar"]').attributes('disabled')).toBeUndefined()
  })

  it('no deja enviar con una imagen fallida hasta reintentar o quitarla', async () => {
    uploadMock.mockRejectedValueOnce(new Error('boom'))
    const wrapper = mount(Composer, { props: { streaming: false } })
    await wrapper.find('textarea').setValue('hola')

    await wrapper.find('textarea').trigger('paste', pasteEvent([image()]))
    await flushPromises()
    expect(wrapper.find('button[aria-label="Enviar"]').attributes('disabled')).toBeDefined()

    await wrapper.find('button[aria-label="Quitar imagen captura.png"]').trigger('click')
    expect(wrapper.find('button[aria-label="Enviar"]').attributes('disabled')).toBeUndefined()
  })

  it('reintentar una subida fallida la completa', async () => {
    uploadMock.mockRejectedValueOnce(new Error('boom'))
    const wrapper = mount(Composer, { props: { streaming: false } })

    await wrapper.find('textarea').trigger('paste', pasteEvent([image()]))
    await flushPromises()
    await wrapper.find('button[aria-label="Reintentar subir captura.png"]').trigger('click')
    await flushPromises()

    expect(uploadMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('button[aria-label="Enviar"]').attributes('disabled')).toBeUndefined()
  })

  it('envía el texto junto con los ids subidos y vacía la tira', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    await wrapper.find('textarea').setValue('  ¿qué dice?  ')
    await wrapper.find('textarea').trigger('paste', pasteEvent([image('a.png')]))
    await flushPromises()

    await wrapper.find('form').trigger('submit')

    const [text, attachments] = wrapper.emitted('send')?.[0] as [string, { id: string }[]]
    expect(text).toBe('¿qué dice?')
    expect(attachments.map((a) => a.id)).toEqual(['id-a.png'])
    expect(wrapper.findAll('.chip')).toHaveLength(0)
  })

  it('permite enviar solo imágenes, sin texto', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    await wrapper.find('textarea').trigger('paste', pasteEvent([image('sola.png')]))
    await flushPromises()

    await wrapper.find('textarea').trigger('keydown', { key: 'Enter' })

    const [text, attachments] = wrapper.emitted('send')?.[0] as [string, { id: string }[]]
    expect(text).toBe('')
    expect(attachments).toHaveLength(1)
  })

  it('quitar una imagen revoca su miniatura', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })
    await wrapper.find('textarea').trigger('paste', pasteEvent([image()]))
    await flushPromises()

    await wrapper.find('button[aria-label="Quitar imagen captura.png"]').trigger('click')

    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview-1')
    expect(wrapper.findAll('.chip')).toHaveLength(0)
  })

  it('devuelve las imágenes de un turno rechazado a la tira', async () => {
    const wrapper = mount(Composer, { props: { streaming: false } })

    await wrapper.setProps({
      restoreAttachments: [
        { id: 'id-9', filename: 'vieja.png', mime: 'image/png', previewUrl: 'blob:vieja' },
      ],
    })

    expect(wrapper.findAll('.chip')).toHaveLength(1)
    expect(wrapper.emitted('restored')).toHaveLength(1)
    expect(wrapper.find('button[aria-label="Enviar"]').attributes('disabled')).toBeUndefined()
  })
})
