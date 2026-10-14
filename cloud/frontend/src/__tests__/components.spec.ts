import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import FreshnessChip from '@/components/FreshnessChip.vue'
import SecretDialog from '@/components/SecretDialog.vue'

describe('SecretDialog', () => {
  it('muestra el secreto con la advertencia de que se ve una sola vez', () => {
    const wrapper = mount(SecretDialog, {
      props: {
        open: true,
        title: 'Token de vinculación',
        secret: 'svk_enr_ABC123',
        instructions: 'Pegalo en SAVI.',
      },
    })

    expect(wrapper.get('[data-test="secret"]').text()).toBe('svk_enr_ABC123')
    expect(wrapper.text()).toContain('una sola vez')
  })

  it('no renderiza nada (ni el secreto) cuando está cerrado', () => {
    const wrapper = mount(SecretDialog, {
      props: { open: false, title: 't', secret: 'svk_enr_SECRETO', instructions: 'x' },
    })

    expect(wrapper.html()).not.toContain('svk_enr_SECRETO')
  })

  it('al confirmar emite close para que el padre descarte el valor', async () => {
    const wrapper = mount(SecretDialog, {
      props: { open: true, title: 't', secret: 's', instructions: 'x' },
    })

    await wrapper.findAll('button').at(-1)?.trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})

describe('ConfirmDialog', () => {
  const base = { open: true, title: 'Revocar', message: 'Es definitivo', confirmLabel: 'Revocar' }

  it('exige escribir la palabra exacta para habilitar el botón', async () => {
    const wrapper = mount(ConfirmDialog, { props: { ...base, typeToConfirm: 'REVOCAR' } })
    const confirm = () => wrapper.findAll('button').at(-1)

    expect(confirm()?.attributes('disabled')).toBeDefined()

    await wrapper.get('input').setValue('revocar')
    expect(confirm()?.attributes('disabled')).toBeDefined() // distingue mayúsculas

    await wrapper.get('input').setValue('REVOCAR')
    expect(confirm()?.attributes('disabled')).toBeUndefined()

    await confirm()?.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('sin palabra a escribir confirma directo', async () => {
    const wrapper = mount(ConfirmDialog, { props: base })

    await wrapper.findAll('button').at(-1)?.trigger('click')

    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('cancelar emite cancel', async () => {
    const wrapper = mount(ConfirmDialog, { props: base })

    await wrapper.findAll('button').at(0)?.trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})

describe('FreshnessChip', () => {
  it('pinta ámbar pasada una hora y rojo pasadas 24 h', () => {
    const warn = mount(FreshnessChip, { props: { seconds: 2 * 3600 } })
    const bad = mount(FreshnessChip, { props: { seconds: 30 * 3600 } })

    expect(warn.get('.badge').classes()).toContain('tone-warn')
    expect(bad.get('.badge').classes()).toContain('tone-bad')
    expect(bad.text()).toContain('Datos hasta hace 30 h')
  })
})
