import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { updatesService } from '../services/updatesService'
import type { UpdateHistory } from '../types'
import { canApplyNow, channelLabel, outcomeLabel, STATUS_CHANGED_EVENT } from '../utils/adminView'
import UpdatesAdminView from '../views/UpdatesAdminView.vue'
import { installRecord, status } from './fixtures'

function history(overrides: Partial<UpdateHistory> = {}): UpdateHistory {
  return {
    channel: 'beta',
    server: 'https://savi-updates.danrodd.dev/savi',
    records: [],
    ...overrides,
  }
}

async function mountView(current = status(), hist = history()) {
  vi.spyOn(updatesService, 'getStatus').mockResolvedValue(current)
  vi.spyOn(updatesService, 'getHistory').mockResolvedValue(hist)
  const wrapper = mount(UpdatesAdminView)
  await flushPromises()
  return wrapper
}

function button(wrapper: Awaited<ReturnType<typeof mountView>>, label: string) {
  return wrapper.findAll('button').find((b) => b.text() === label)
}

describe('UpdatesAdminView', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the installed version, channel, server and what is available', async () => {
    const wrapper = await mountView()

    expect(wrapper.get('[data-testid="current-version"]').text()).toBe('v1.3.2')
    expect(wrapper.get('[data-testid="available-version"]').text()).toBe('v1.4.0')
    expect(wrapper.text()).toContain('Beta (pruebas de SEO)')
    expect(wrapper.text()).toContain('https://savi-updates.danrodd.dev/savi')
    expect(wrapper.get('[data-testid="update-notes"]').text()).toContain('pantalla en blanco')
  })

  it('renders the release notes as markdown, not as raw text', async () => {
    const wrapper = await mountView(
      status({
        notes: '## Funcionalidades\n\n- **updates**: descarga que se retoma\n- <script>x</script>',
      }),
    )
    const notes = wrapper.get('[data-testid="update-notes"]')

    expect(notes.find('h2').text()).toBe('Funcionalidades')
    expect(notes.findAll('li')).toHaveLength(2)
    expect(notes.find('strong').text()).toBe('updates')
    expect(notes.text()).not.toContain('##')
    expect(notes.find('script').exists()).toBe(false)
  })

  it('says so when there are no attempts yet', async () => {
    const wrapper = await mountView()

    expect(wrapper.find('[data-testid="history-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="history-table"]').exists()).toBe(false)
  })

  it('lists every attempt with its result and detail', async () => {
    const wrapper = await mountView(
      status(),
      history({
        records: [
          installRecord({
            attempt_id: 'a2',
            outcome: 'failed',
            exit_code: 4,
            message: 'La actualización a v1.4.0 no se completó: la instalación falló.',
          }),
          installRecord({ attempt_id: 'a1' }),
        ],
      }),
    )

    const rows = wrapper.findAll('[data-testid="history-table"] tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.text()).toContain('Falló')
    expect(rows[0]?.text()).toContain('la instalación falló')
    expect(rows[1]?.text()).toContain('Instalada')
    expect(rows[1]?.text()).toContain('v1.3.2')
  })

  it('"Buscar ahora" refreshes the status and tells the global notice', async () => {
    const wrapper = await mountView(status({ state: 'up_to_date', available_version: null }))
    const check = vi
      .spyOn(updatesService, 'check')
      .mockResolvedValue(status({ available_version: 'v1.4.1' }))
    const changed = vi.fn()
    window.addEventListener(STATUS_CHANGED_EVENT, changed)

    await button(wrapper, 'Buscar ahora')?.trigger('click')
    await flushPromises()

    expect(check).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-testid="available-version"]').text()).toBe('v1.4.1')
    expect(changed).toHaveBeenCalledOnce()
    window.removeEventListener(STATUS_CHANGED_EVENT, changed)
  })

  it('"Actualizar ahora" starts the same flow as the notice', async () => {
    const wrapper = await mountView()
    const apply = vi
      .spyOn(updatesService, 'apply')
      .mockResolvedValue(status({ phase: 'downloading' }))

    await button(wrapper, 'Actualizar ahora')?.trigger('click')
    await flushPromises()

    expect(apply).toHaveBeenCalledOnce()
  })

  it('does not offer to update when there is nothing to install', async () => {
    const wrapper = await mountView(status({ state: 'up_to_date', available_version: null }))

    expect(button(wrapper, 'Actualizar ahora')).toBeUndefined()
    expect(button(wrapper, 'Buscar ahora')).toBeDefined()
  })

  it('explains when updates are not active on this installation', async () => {
    const wrapper = await mountView(
      status({ enabled: false, current_version: null, available_version: null }),
      history({ server: '' }),
    )

    expect(wrapper.find('[data-testid="updates-disabled"]').exists()).toBe(true)
    expect(button(wrapper, 'Buscar ahora')).toBeUndefined()
  })

  it('shows an error when the status cannot be read', async () => {
    vi.spyOn(updatesService, 'getStatus').mockRejectedValue(new Error('caído'))
    vi.spyOn(updatesService, 'getHistory').mockResolvedValue(history())
    const wrapper = mount(UpdatesAdminView)
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('No se pudo leer')
  })
})

describe('reglas de la vista de Administración', () => {
  it('names every outcome', () => {
    expect(outcomeLabel('rolled_back')).toBe('Revertida')
    expect(outcomeLabel('timeout')).toBe('Sin respuesta')
    expect(channelLabel('stable')).toBe('Estable')
  })

  it('only offers to update when idle or failed, with something to install', () => {
    expect(canApplyNow(status())).toBe(true)
    expect(canApplyNow(status({ phase: 'failed' }))).toBe(true)
    expect(canApplyNow(status({ phase: 'downloading' }))).toBe(false)
    expect(canApplyNow(status({ state: 'up_to_date' }))).toBe(false)
    expect(canApplyNow(status({ can_apply: false }))).toBe(false)
    expect(canApplyNow(status({ enabled: false }))).toBe(false)
  })
})
