import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HttpClient, HttpRequestError } from '@/lib/HttpClient'
import type { MessageSource } from '../../types'
import { linkCitations, referenceNumbers, webSourceLink } from '../../utils/citations'
import MessageSources from '../MessageSources.vue'

vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }))

const source = (overrides: Partial<MessageSource> = {}): MessageSource => ({
  ref: 'D1',
  refs: ['D1'],
  document_id: 'doc-1',
  version: 1,
  title: 'Manual de caja',
  pages: '3-4',
  ...overrides,
})

describe('linkCitations', () => {
  const sources = [
    source(),
    source({ ref: 'D2', refs: ['D2', 'D3'], document_id: 'doc-2', title: 'Política' }),
  ]

  it('numera por documento, en el orden de las fuentes', () => {
    expect(linkCitations('Firma el supervisor [D2]. Cierre [D1] y arqueo [D3].', sources)).toBe(
      'Firma el supervisor². Cierre¹ y arqueo².',
    )
  })

  it('elimina referencias inventadas', () => {
    expect(linkCitations('Dato real [D1]. Dato inventado [D9].', sources)).toBe(
      'Dato real¹. Dato inventado.',
    )
  })

  it('oculta las referencias mientras las fuentes no llegaron', () => {
    expect(linkCitations('Respuesta en curso [D1]', undefined)).toBe('Respuesta en curso')
  })

  it('conserva el espacio después de un cierre de formato para no romper el negrita', () => {
    expect(linkCitations('El tope es **7,5 %** [D1].', sources)).toBe('El tope es **7,5 %** ¹.')
  })

  it('no toca bloques de código', () => {
    const text = 'Uso: [D1]\n\n```\nlista[D1]\n```'
    expect(linkCitations(text, sources)).toBe('Uso:¹\n\n```\nlista[D1]\n```')
  })

  it('asigna un número a cada referencia del documento', () => {
    expect([...referenceNumbers(sources)]).toEqual([
      ['D1', 1],
      ['D2', 2],
      ['D3', 2],
    ])
  })
})

describe('MessageSources', () => {
  afterEach(() => vi.restoreAllMocks())

  it('lista la fuente con páginas y permite abrirla', () => {
    const wrapper = mount(MessageSources, {
      props: { sources: [source()], conversationId: 'c1', readOnly: false },
    })
    expect(wrapper.text()).toContain('Manual de caja')
    expect(wrapper.text()).toContain('p. 3-4')
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('muestra eliminado y no ofrece abrir', () => {
    const wrapper = mount(MessageSources, {
      props: {
        sources: [source({ available: false, unavailable_reason: 'deleted' })],
        conversationId: 'c1',
        readOnly: false,
      },
    })
    expect(wrapper.text()).toContain('(eliminado)')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('en una conversación compartida lista las fuentes sin abrirlas', () => {
    const wrapper = mount(MessageSources, {
      props: { sources: [source()], conversationId: 'c1', readOnly: true },
    })
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('abre el original con autenticación y la conversación como contexto', async () => {
    const getBlob = vi.spyOn(HttpClient.prototype, 'getBlob').mockResolvedValue(new Blob(['pdf']))
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:doc')
    globalThis.URL.revokeObjectURL = vi.fn()

    const wrapper = mount(MessageSources, {
      props: { sources: [source()], conversationId: 'c1', readOnly: false },
    })
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(getBlob).toHaveBeenCalledWith('/doc-1/file', { query: { conversation_id: 'c1' } })
    expect(open).toHaveBeenCalledWith('blob:doc#page=3', '_blank', 'noopener')
  })

  it('un 404 marca la fuente como no disponible', async () => {
    vi.spyOn(HttpClient.prototype, 'getBlob').mockRejectedValue(
      new HttpRequestError('Not found', 404),
    )
    const wrapper = mount(MessageSources, {
      props: { sources: [source()], conversationId: 'c1', readOnly: false },
    })
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).toContain('(no disponible)')
  })
})

describe('fuentes web', () => {
  const web = source({
    title: 'Tarifas',
    pages: null,
    url: 'https://www.surandina.com.co/tarifas.html',
  })

  it('se abren con su link público, también en la vista compartida', () => {
    const wrapper = mount(MessageSources, {
      props: { sources: [web], conversationId: null, readOnly: true },
    })
    const link = wrapper.get('a.sources__link')
    expect(link.attributes('href')).toBe('https://www.surandina.com.co/tarifas.html')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
    expect(wrapper.text()).toContain('surandina.com.co')
  })

  it('una fuente web eliminada no se enlaza', () => {
    const wrapper = mount(MessageSources, {
      props: {
        sources: [{ ...web, available: false, unavailable_reason: 'deleted' }],
        conversationId: 'conv-1',
        readOnly: false,
      },
    })
    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.text()).toContain('eliminado')
  })

  it('solo acepta links http(s)', () => {
    expect(webSourceLink('javascript:alert(1)')).toBeNull()
    expect(webSourceLink('no es url')).toBeNull()
    expect(webSourceLink(null)).toBeNull()
    expect(webSourceLink('http://empresa.com/a')).toEqual({
      href: 'http://empresa.com/a',
      host: 'empresa.com',
    })
  })
})
