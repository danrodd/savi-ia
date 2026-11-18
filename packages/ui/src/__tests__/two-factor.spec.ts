import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TwoFactorPanel from '../components/TwoFactorPanel.vue'

const QR = 'data:image/png;base64,AAAA'
const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
})

describe('TwoFactorPanel', () => {
  it('al configurar muestra los tres pasos y el QR, con la clave plegada', () => {
    const wrapper = mount(TwoFactorPanel, { props: { mode: 'setup', qr: QR, secret: SECRET } })

    expect(wrapper.text()).toContain('Proteja su cuenta')
    expect(wrapper.findAll('.ui-2fa__step')).toHaveLength(3)
    expect(wrapper.get('[data-test="two-factor-qr"]').attributes('src')).toBe(QR)
    expect(wrapper.find('[data-test="two-factor-secret"]').exists()).toBe(false)
  })

  it('la clave se muestra en bloques de cuatro y se copia sin espacios', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const wrapper = mount(TwoFactorPanel, { props: { mode: 'setup', qr: QR, secret: SECRET } })

    await wrapper.get('[data-test="two-factor-show-key"]').trigger('click')
    expect(wrapper.get('[data-test="two-factor-secret"]').text()).toBe(
      'JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP',
    )
    await wrapper.get('[data-test="two-factor-copy"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(SECRET)
    expect(wrapper.get('[data-test="two-factor-copy"]').text()).toContain('Copiada')
  })

  it('sin QR todavía no deja escribir el código', () => {
    const wrapper = mount(TwoFactorPanel, { props: { mode: 'setup', qr: null, secret: null } })
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Preparando')
  })

  it('al verificar emite el código completo y muestra cuánto falta para que cambie', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-18T12:00:18Z'))
    const wrapper = mount(TwoFactorPanel, {
      props: {
        mode: 'verify' as const,
        code: '',
        'onUpdate:code': (v: string) => wrapper.setProps({ code: v }),
      },
      attachTo: document.body,
    })

    await flushPromises()
    expect(wrapper.get('[data-test="two-factor-timer"]').text()).toContain('12 s')
    const cells = wrapper.findAll('input')
    for (const [i, digit] of ['1', '2', '3', '4', '5', '6'].entries()) {
      await cells[i]?.setValue(digit)
    }
    expect(wrapper.emitted('complete')).toEqual([['123456']])
  })

  it('ofrece ayuda para quien no tiene el celular y un botón para volver', async () => {
    const wrapper = mount(TwoFactorPanel, {
      props: { mode: 'verify', recoveryHint: 'Pida ayuda a soporte.' },
    })
    expect(wrapper.text()).toContain('¿No tiene su celular a mano?')
    expect(wrapper.text()).toContain('Pida ayuda a soporte.')
    await wrapper.get('.ui-2fa__back').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})
