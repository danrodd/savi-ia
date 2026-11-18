import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Alert } from '@/lib/types'

const api = vi.hoisted(() => ({
  alertSummary: vi.fn(),
  alerts: vi.fn(),
  alertRules: vi.fn(),
}))
const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

import AlertBell from '@/components/AlertBell.vue'
import AppLayout from '@/components/AppLayout.vue'
import {
  freshAlerts,
  openAlertList,
  refreshOpenAlerts,
  resetOpenAlertsForTests,
} from '@/composables/useOpenAlerts'
import { resetRuleTitlesForTests } from '@/lib/ruleTitles'
import { useAuthStore } from '@/stores/authStore'

function alert(id: string, severity: Alert['severity'], opened: string): Alert {
  return {
    id,
    rule_code: 'instance_offline',
    severity,
    status: 'open',
    client_id: 'c1',
    client_name: 'Llantas Uno',
    instance_id: null,
    details: {},
    opened_at: opened,
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    resolution_note: null,
  }
}

const OLD = alert('a1', 'warning', '2026-11-18T08:00:00Z')
const NEW_CRITICAL = alert('a2', 'critical', '2026-11-18T09:00:00Z')
const NEW_INFO = alert('a3', 'info', '2026-11-18T09:05:00Z')

function router() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:p(.*)*', component: { template: '<div />' }, meta: { title: 'Resumen' } }],
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  resetOpenAlertsForTests()
  resetRuleTitlesForTests()
  document.body.innerHTML = ''
  document.title = 'Resumen · SAVI Cloud'
  api.alertRules.mockResolvedValue([{ code: 'instance_offline', title: 'Instancia sin conexión' }])
  api.alertSummary.mockResolvedValue({ open: 1, acknowledged: 0 })
  api.alerts.mockResolvedValue([OLD])
})

describe('alertas abiertas', () => {
  it('la primera lectura fija la base y la siguiente marca solo las nuevas', async () => {
    await refreshOpenAlerts()
    expect(freshAlerts.value).toEqual([])

    api.alerts.mockResolvedValue([OLD, NEW_CRITICAL])
    await refreshOpenAlerts()
    expect(freshAlerts.value.map((a) => a.id)).toEqual(['a2'])
    // La lista va de la más nueva a la más vieja.
    expect(openAlertList.value.map((a) => a.id)).toEqual(['a2', 'a1'])

    await refreshOpenAlerts()
    expect(freshAlerts.value).toEqual([])
  })
})

describe('campana de avisos', () => {
  it('muestra el conteo y las últimas alertas con su cliente', async () => {
    api.alertSummary.mockResolvedValue({ open: 2, acknowledged: 0 })
    api.alerts.mockResolvedValue([OLD, NEW_CRITICAL])
    await refreshOpenAlerts()
    const wrapper = mount(AlertBell, { global: { plugins: [router()] }, attachTo: document.body })
    await flushPromises()

    const bell = wrapper.get('[data-test="alert-bell"]')
    expect(bell.attributes('aria-label')).toBe('Avisos: 2 alertas abiertas')
    await bell.trigger('click')
    await flushPromises()

    const feed = document.querySelector('[data-test="alert-feed"]')
    expect(feed?.textContent).toContain('Instancia sin conexión')
    expect(feed?.textContent).toContain('Llantas Uno')
    expect(feed?.querySelector('a')?.getAttribute('href')).toBe('/clientes/c1/alertas')
  })
})

describe('avisos en la consola', () => {
  async function mountLayout() {
    const auth = useAuthStore()
    auth.user = {
      id: 's1',
      email: 'a@seo.example',
      full_name: 'Ana',
      role: 'admin',
      permissions: ['alerts.read', 'overview.read'] as never,
    }
    auth.accessToken = 'tok'
    const r = router()
    await r.push('/')
    const wrapper = mount(AppLayout, { global: { plugins: [r] }, attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  it('avisa las críticas nuevas, no las informativas, y pone el conteo en la pestaña', async () => {
    const wrapper = await mountLayout()
    expect(toast.error).not.toHaveBeenCalled() // la base no avisa
    expect(document.title).toBe('(1) Resumen · SAVI Cloud')

    api.alertSummary.mockResolvedValue({ open: 3, acknowledged: 0 })
    api.alerts.mockResolvedValue([OLD, NEW_CRITICAL, NEW_INFO])
    await refreshOpenAlerts()
    await flushPromises()

    expect(toast.error).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledWith(
      'Instancia sin conexión',
      expect.objectContaining({ description: 'Llantas Uno', action: expect.anything() }),
    )
    expect(toast.warning).not.toHaveBeenCalled()
    expect(document.title).toBe('(3) Resumen · SAVI Cloud')
    wrapper.unmount()
  })
})
