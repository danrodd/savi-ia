import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ShareMenu from '../ShareMenu.vue'

vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }))

const base = { text: 'Respuesta', conversationId: 'c-1', contentEl: null }

describe('ShareMenu', () => {
  it('el botón de cada respuesta dice "Compartir", no "Enviar"', () => {
    const wrapper = mount(ShareMenu, { props: { ...base, kind: 'message' } })

    const trigger = wrapper.find('button')
    expect(trigger.text()).toBe('Compartir')
    expect(trigger.attributes('aria-label')).toBe('Copiar o enviar esta respuesta')
    // "Enviar" es solo el botón del composer.
    expect(wrapper.text()).not.toContain('Enviar')
  })

  it('el de la conversación completa se distingue por su nombre', () => {
    const wrapper = mount(ShareMenu, { props: { ...base, kind: 'conversation' } })

    const trigger = wrapper.find('button')
    expect(trigger.text()).toBe('Compartir conversación')
    expect(trigger.attributes('aria-label')).toBe('Compartir conversación')
  })
})
