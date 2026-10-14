import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { MessageFeedback } from '../../types'
import { resolveFeedbackClick } from '../../utils/feedback'

const rateMessage = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('../../stores/chatStore', () => ({ useChatStore: () => ({ rateMessage }) }))
vi.mock('@/lib/toast', () => ({ toast: toastMock }))

import FeedbackButtons from '../FeedbackButtons.vue'

// El diálogo se teletransporta: se prueba con el DOM del documento.
function mountButtons(feedback: MessageFeedback | null = null) {
  return mount(FeedbackButtons, {
    props: { messageId: 'm-1', feedback },
    attachTo: document.body,
  })
}

function dialog(): HTMLElement | null {
  return document.querySelector('[data-testid="feedback-dialog"]')
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  rateMessage.mockResolvedValue(true)
  document.body.innerHTML = ''
})

describe('resolveFeedbackClick', () => {
  it('👍 guarda directo', () => {
    expect(resolveFeedbackClick(null, 'up')).toEqual({ kind: 'save', input: { rating: 'up' } })
  })

  it('👎 pide el motivo', () => {
    expect(resolveFeedbackClick(null, 'down')).toEqual({ kind: 'ask-reason' })
  })

  it('tocar la calificación activa la quita', () => {
    const up = { rating: 'up', reason: null, comment: null } as const
    expect(resolveFeedbackClick(up, 'up')).toEqual({ kind: 'clear' })
  })

  it('cambiar de 👎 a 👍 guarda 👍', () => {
    const down = { rating: 'down', reason: 'otra', comment: null } as const
    expect(resolveFeedbackClick(down, 'up')).toEqual({ kind: 'save', input: { rating: 'up' } })
  })
})

describe('FeedbackButtons', () => {
  it('tiene los dos botones con sus nombres accesibles', () => {
    const wrapper = mountButtons()

    expect(wrapper.find('[aria-label="Me sirvió"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="No me sirvió"]').exists()).toBe(true)
  })

  it('refleja la calificación activa con aria-pressed', () => {
    const wrapper = mountButtons({ rating: 'down', reason: 'otra', comment: null })

    expect(wrapper.find('[data-testid="feedback-up"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.find('[data-testid="feedback-down"]').attributes('aria-pressed')).toBe('true')
  })

  it('👍 guarda en el acto y agradece', async () => {
    const wrapper = mountButtons()

    await wrapper.find('[data-testid="feedback-up"]').trigger('click')
    await flushPromises()

    expect(rateMessage).toHaveBeenCalledWith('m-1', { rating: 'up' })
    expect(toastMock.success).toHaveBeenCalledWith('¡Gracias!')
  })

  it('tocar 👍 estando activo lo quita', async () => {
    const wrapper = mountButtons({ rating: 'up', reason: null, comment: null })

    await wrapper.find('[data-testid="feedback-up"]').trigger('click')
    await flushPromises()

    expect(rateMessage).toHaveBeenCalledWith('m-1', null)
  })

  it('👎 abre el diálogo sin guardar todavía', async () => {
    const wrapper = mountButtons()

    await wrapper.find('[data-testid="feedback-down"]').trigger('click')
    await flushPromises()

    expect(rateMessage).not.toHaveBeenCalled()
    const form = dialog()
    expect(form).not.toBeNull()
    expect(document.body.textContent).toContain('¿Qué pasó?')
    for (const label of [
      'El dato es incorrecto',
      'No entendió mi pregunta',
      'Está incompleta',
      'Tardó demasiado',
      'Otra cosa',
    ]) {
      expect(form?.textContent).toContain(label)
    }
    expect(document.body.textContent).toContain('Contanos más (opcional)')
  })

  it('Enviar guarda 👎 con motivo y comentario', async () => {
    const wrapper = mountButtons()
    await wrapper.find('[data-testid="feedback-down"]').trigger('click')
    await flushPromises()

    const radios = document.querySelectorAll<HTMLInputElement>('input[type="radio"]')
    radios[2]?.click()
    const textarea = document.querySelector<HTMLTextAreaElement>('textarea')
    if (textarea) {
      textarea.value = 'Faltó el IVA'
      textarea.dispatchEvent(new Event('input'))
    }
    dialog()?.dispatchEvent(new Event('submit', { cancelable: true }))
    await flushPromises()

    expect(rateMessage).toHaveBeenCalledWith('m-1', {
      rating: 'down',
      reason: 'incompleta',
      comment: 'Faltó el IVA',
    })
    expect(dialog()).toBeNull()
  })

  it('Cancelar cierra sin guardar', async () => {
    const wrapper = mountButtons()
    await wrapper.find('[data-testid="feedback-down"]').trigger('click')
    await flushPromises()

    const cancel = [...document.querySelectorAll('button')].find(
      (b) => b.textContent?.trim() === 'Cancelar',
    )
    cancel?.click()
    await flushPromises()

    expect(rateMessage).not.toHaveBeenCalled()
    expect(dialog()).toBeNull()
  })

  it('si guardar falla avisa y el diálogo sigue abierto', async () => {
    rateMessage.mockResolvedValue(false)
    const wrapper = mountButtons()
    await wrapper.find('[data-testid="feedback-down"]').trigger('click')
    await flushPromises()

    dialog()?.dispatchEvent(new Event('submit', { cancelable: true }))
    await flushPromises()

    expect(toastMock.error).toHaveBeenCalled()
    expect(dialog()).not.toBeNull()
  })
})
