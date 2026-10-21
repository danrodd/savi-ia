import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import UpdateNotice from '../components/UpdateNotice.vue'
import { updatesService } from '../services/updatesService'
import { status } from './fixtures'

describe('UpdateNotice', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  async function mountWith(current: ReturnType<typeof status>) {
    vi.spyOn(updatesService, 'getStatus').mockResolvedValue(current)
    const wrapper = mount(UpdateNotice, { attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  it('offers to update and restart a recommended version', async () => {
    const apply = vi
      .spyOn(updatesService, 'apply')
      .mockResolvedValue(status({ phase: 'downloading' }))
    const wrapper = await mountWith(status())

    expect(wrapper.text()).toContain('Hay una versión nueva de SAVI (v1.4.0).')
    const button = wrapper.findAll('button').find((b) => b.text() === 'Actualizar y reiniciar')
    await button?.trigger('click')
    await flushPromises()

    expect(apply).toHaveBeenCalledOnce()
    expect(document.body.textContent).toContain('Descargando la actualización')
    wrapper.unmount()
  })

  it('hides the banner with "Más tarde"', async () => {
    const wrapper = await mountWith(status())
    const later = wrapper.findAll('button').find((b) => b.text() === 'Más tarde')
    await later?.trigger('click')
    expect(wrapper.text()).not.toContain('Hay una versión nueva')
    wrapper.unmount()
  })

  it('asks remote browsers to contact IT instead of updating', async () => {
    const wrapper = await mountWith(status({ can_apply: false }))
    expect(wrapper.text()).toContain('Avise a su área de sistemas')
    expect(wrapper.text()).not.toContain('Actualizar y reiniciar')
    wrapper.unmount()
  })

  it('blocks with a dialog that cannot be closed', async () => {
    const wrapper = await mountWith(status({ state: 'blocked' }))
    expect(document.body.textContent).toContain('Esta versión de SAVI ya no es compatible.')
    expect(document.body.querySelector('[aria-label="Cerrar"]')).toBeNull()
    wrapper.unmount()
  })

  it('shows nothing when updates are disabled', async () => {
    const wrapper = await mountWith(status({ enabled: false }))
    expect(wrapper.text()).toBe('')
    wrapper.unmount()
  })
})
