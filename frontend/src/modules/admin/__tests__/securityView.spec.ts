import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const reset = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn(), error: vi.fn() }))

vi.mock('../services/mfaAdminService', () => ({ mfaAdminService: { reset } }))
vi.mock('@/lib/toast', () => ({ toast }))

import SecurityView from '../views/SecurityView.vue'

beforeEach(() => vi.clearAllMocks())

describe('SecurityView', () => {
  it('no permite restablecer sin indicar el usuario', () => {
    const wrapper = mount(SecurityView)

    const button = wrapper.get('button[type="submit"]')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('pide confirmación antes de llamar al backend', async () => {
    const wrapper = mount(SecurityView, { attachTo: document.body })

    await wrapper.get('[data-testid="mfa-reset-login"]').setValue('  JPEREZ@NORTE ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(reset).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('JPEREZ@NORTE')
    wrapper.unmount()
  })
})
