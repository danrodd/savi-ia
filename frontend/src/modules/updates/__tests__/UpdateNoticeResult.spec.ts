import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { STORAGE_KEYS } from '@/lib/storageKeys'
import UpdateNotice from '../components/UpdateNotice.vue'
import { updatesService } from '../services/updatesService'
import { INSTALLING_MAX_MS, STALLED_MESSAGE } from '../utils/updateView'
import { installRecord, status } from './fixtures'

const upToDate = { state: 'up_to_date', available_version: null } as const

describe('UpdateNotice: resultado de la instalación', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  async function mountWith(current: ReturnType<typeof status>) {
    vi.spyOn(updatesService, 'getStatus').mockResolvedValue(current)
    const wrapper = mount(UpdateNotice, { attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  it('tells once that SAVI was updated', async () => {
    const wrapper = await mountWith(status({ ...upToDate, last_install: installRecord() }))

    expect(wrapper.text()).toContain('SAVI se actualizó a v1.4.0.')
    const dismiss = wrapper.findAll('button').find((b) => b.text() === 'Entendido')
    await dismiss?.trigger('click')

    expect(wrapper.text()).not.toContain('SAVI se actualizó')
    expect(window.localStorage.getItem(STORAGE_KEYS.UPDATE_RESULT_SEEN)).toBe('a1')
    wrapper.unmount()

    const again = await mountWith(status({ ...upToDate, last_install: installRecord() }))
    expect(again.text()).not.toContain('SAVI se actualizó')
    again.unmount()
  })

  it('shows a new attempt even if an older one was already seen', async () => {
    window.localStorage.setItem(STORAGE_KEYS.UPDATE_RESULT_SEEN, 'a0')
    const wrapper = await mountWith(status({ ...upToDate, last_install: installRecord() }))

    expect(wrapper.text()).toContain('SAVI se actualizó a v1.4.0.')
    wrapper.unmount()
  })

  it('warns that the update did not complete, next to the pending update', async () => {
    const message =
      'La actualización a v1.4.0 no se completó: la instalación falló. SAVI sigue en v1.3.2.'
    const wrapper = await mountWith(
      status({
        last_install: installRecord({ outcome: 'failed', exit_code: 4, message }),
      }),
    )

    const result = wrapper.get('[data-testid="update-result"]')
    expect(result.text()).toContain(message)
    expect(result.classes()).toContain('update-banner--warning')
    expect(wrapper.text()).toContain('Hay una versión nueva de SAVI (v1.4.0).')
    wrapper.unmount()
  })

  it('does not repeat a cancellation the person already saw', async () => {
    const wrapper = await mountWith(
      status({ last_install: installRecord({ outcome: 'cancelled', exit_code: null }) }),
    )

    expect(wrapper.find('[data-testid="update-result"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not duplicate a failure that already has its message in the bar', async () => {
    const wrapper = await mountWith(
      status({
        phase: 'failed',
        error: 'Se canceló el permiso de administrador: SAVI sigue en v1.3.2.',
        last_install: installRecord({ outcome: 'failed', message: 'otro texto' }),
      }),
    )

    expect(wrapper.find('[data-testid="update-result"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Se canceló el permiso de administrador')
    wrapper.unmount()
  })
})

describe('UpdateNotice: esperar a que SAVI vuelva', () => {
  beforeEach(() => {
    window.localStorage.clear()
    // `setImmediate` queda real: `flushPromises` lo necesita.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  async function mountInstalling() {
    const getStatus = vi
      .spyOn(updatesService, 'getStatus')
      .mockResolvedValue(status({ phase: 'installing' }))
    const wrapper = mount(UpdateNotice, { attachTo: document.body })
    await flushPromises()
    expect(document.body.textContent).toContain('Instalando la actualización')
    return { wrapper, getStatus }
  }

  it('leaves the wait when SAVI comes back on the same version without having updated', async () => {
    const { wrapper, getStatus } = await mountInstalling()
    vi.spyOn(updatesService, 'healthVersion').mockResolvedValue('v1.3.2')
    getStatus.mockResolvedValue(
      status({
        phase: 'idle',
        last_install: installRecord({
          outcome: 'failed',
          message: 'La actualización a v1.4.0 no se completó. SAVI sigue en v1.3.2.',
        }),
      }),
    )

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(document.body.textContent).not.toContain('Actualizando SAVI')
    expect(wrapper.text()).toContain('no se completó')
    wrapper.unmount()
  })

  it('keeps waiting while the same process is still installing', async () => {
    const { wrapper } = await mountInstalling()
    vi.spyOn(updatesService, 'healthVersion').mockResolvedValue('v1.3.2')

    await vi.advanceTimersByTimeAsync(10_000)
    await flushPromises()

    expect(document.body.textContent).toContain('Actualizando SAVI')
    wrapper.unmount()
  })

  it('reloads when SAVI answers with the new version', async () => {
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    const { wrapper } = await mountInstalling()
    vi.spyOn(updatesService, 'healthVersion').mockResolvedValue('v1.4.0')

    await vi.advanceTimersByTimeAsync(2000)

    expect(reload).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('warns when SAVI takes too long and lets the person stop waiting', async () => {
    const { wrapper } = await mountInstalling()
    vi.spyOn(updatesService, 'healthVersion').mockResolvedValue(null)
    expect(document.body.textContent).not.toContain(STALLED_MESSAGE)

    await vi.advanceTimersByTimeAsync(INSTALLING_MAX_MS + 10_000)
    await flushPromises()

    expect(document.body.textContent).toContain(STALLED_MESSAGE)
    const giveUp = Array.from(document.body.querySelectorAll('button')).find(
      (b) => b.textContent?.trim() === 'Dejar de esperar',
    )
    expect(giveUp).toBeDefined()
    giveUp?.click()
    await flushPromises()

    expect(document.body.textContent).not.toContain('Actualizando SAVI')
    wrapper.unmount()
  })
})
