import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import FreshnessChip from '@/components/FreshnessChip.vue'
import SecretDialog from '@/components/SecretDialog.vue'

const global = {}

describe('SecretDialog', () => {
  it('muestra el secreto con la advertencia de que se ve una sola vez', () => {
    const wrapper = mount(SecretDialog, {
      props: {
        open: true,
        title: 'Token de vinculación',
        secret: 'svk_enr_ABC123',
        instructions: 'Pegalo en SAVI.',
      },
      global,
    })

    expect(wrapper.get('[data-test="secret"] code').text()).toBe('svk_enr_ABC123')
    expect(wrapper.text()).toContain('una sola vez')
  })

  it('no renderiza nada (ni el secreto) cuando está cerrado', () => {
    const wrapper = mount(SecretDialog, {
      props: { open: false, title: 't', secret: 'svk_enr_SECRETO', instructions: 'x' },
      global,
    })

    expect(wrapper.html()).not.toContain('svk_enr_SECRETO')
  })

  it('no ofrece la X de cerrar: solo "Ya lo guardé"', () => {
    const wrapper = mount(SecretDialog, {
      props: { open: true, title: 't', secret: 's', instructions: 'x' },
      global,
    })

    expect(wrapper.find('[aria-label="Cerrar"]').exists()).toBe(false)
  })

  it('al confirmar emite close para que el padre descarte el valor', async () => {
    const wrapper = mount(SecretDialog, {
      props: { open: true, title: 't', secret: 's', instructions: 'x' },
      global,
    })

    await wrapper.get('[data-test="secret-close"]').trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})

describe('ConfirmDialog', () => {
  const base = { open: true, title: 'Revocar', message: 'Es definitivo', confirmLabel: 'Revocar' }
  const accept = (wrapper: ReturnType<typeof mount>) => wrapper.get('[data-test="confirm-accept"]')

  it('exige escribir la palabra exacta para habilitar el botón', async () => {
    const wrapper = mount(ConfirmDialog, { props: { ...base, typeToConfirm: 'REVOCAR' }, global })

    expect(accept(wrapper).attributes('disabled')).toBeDefined()

    await wrapper.get('input').setValue('revocar')
    expect(accept(wrapper).attributes('disabled')).toBeDefined() // distingue mayúsculas

    await wrapper.get('input').setValue('REVOCAR')
    expect(accept(wrapper).attributes('disabled')).toBeUndefined()

    await accept(wrapper).trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('sin palabra a escribir confirma directo', async () => {
    const wrapper = mount(ConfirmDialog, { props: base, global })

    await accept(wrapper).trigger('click')

    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('cancelar emite cancel', async () => {
    const wrapper = mount(ConfirmDialog, { props: base, global })

    await wrapper.get('[data-test="confirm-cancel"]').trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('mientras el padre ejecuta la acción no se puede confirmar de nuevo', () => {
    const wrapper = mount(ConfirmDialog, { props: { ...base, busy: true }, global })

    expect(accept(wrapper).attributes('disabled')).toBeDefined()
  })
})

describe('FreshnessChip', () => {
  it('pinta ámbar pasada una hora y rojo pasadas 24 h', () => {
    const warn = mount(FreshnessChip, { props: { seconds: 2 * 3600 } })
    const bad = mount(FreshnessChip, { props: { seconds: 30 * 3600 } })

    expect(warn.get('.ui-badge').classes()).toContain('ui-badge--warning')
    expect(bad.get('.ui-badge').classes()).toContain('ui-badge--danger')
    expect(bad.text()).toContain('Datos hasta hace 30 h')
  })
})
