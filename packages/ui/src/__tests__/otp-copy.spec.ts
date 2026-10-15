import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CopyField from '../components/CopyField.vue'
import OtpInput from '../components/OtpInput.vue'

function mountOtp(modelValue = '') {
  const wrapper = mount(OtpInput, {
    props: {
      modelValue,
      'onUpdate:modelValue': (value: string) => wrapper.setProps({ modelValue: value }),
    },
    attachTo: document.body,
  })
  return wrapper
}

describe('OtpInput', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('arma el código dígito a dígito y emite complete al llenarse', async () => {
    const wrapper = mountOtp()
    const cells = wrapper.findAll('input')
    expect(cells).toHaveLength(6)
    for (const [i, digit] of ['1', '2', '3', '4', '5', '6'].entries()) {
      await cells[i]?.setValue(digit)
    }
    expect(wrapper.props('modelValue')).toBe('123456')
    expect(wrapper.emitted('complete')).toEqual([['123456']])
  })

  it('acepta el código pegado entero, ignorando lo que no es dígito', async () => {
    const wrapper = mountOtp()
    await wrapper.findAll('input')[0]?.trigger('paste', {
      clipboardData: { getData: () => '123 456' },
    })
    expect(wrapper.props('modelValue')).toBe('123456')
    expect(wrapper.emitted('complete')).toEqual([['123456']])
  })

  it('ignora letras', async () => {
    const wrapper = mountOtp()
    await wrapper.findAll('input')[0]?.setValue('a')
    expect(wrapper.props('modelValue')).toBe('')
  })

  it('Backspace borra el dígito anterior si la casilla está vacía', async () => {
    const wrapper = mountOtp('12')
    await wrapper.findAll('input')[2]?.trigger('keydown', { key: 'Backspace' })
    expect(wrapper.props('modelValue')).toBe('1')
  })

  it('clear() vacía las casillas', async () => {
    const wrapper = mountOtp('123456')
    ;(wrapper.vm as unknown as { clear: () => void }).clear()
    await flushPromises()
    expect(wrapper.props('modelValue')).toBe('')
  })

  it('cada casilla tiene una etiqueta accesible', () => {
    const wrapper = mountOtp()
    expect(wrapper.findAll('input')[0]?.attributes('aria-label')).toBe('Dígito 1 de 6')
    expect(wrapper.get('legend').text()).toBe('Código de verificación')
  })
})

describe('CopyField', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('copia el valor y confirma', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(CopyField, { props: { value: 'JBSWY3DPEHPK3PXP', label: 'Secreto' } })

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('JBSWY3DPEHPK3PXP')
    expect(wrapper.get('button').text()).toContain('Copiado')
    expect(wrapper.emitted('copied')).toHaveLength(1)
  })

  it('si el portapapeles falla no dice "Copiado"', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('x')) },
    })
    const wrapper = mount(CopyField, { props: { value: 'abc' } })

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.get('button').text()).toContain('Copiar')
    expect(wrapper.emitted('copied')).toBeUndefined()
  })
})
