import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EnrollmentToken } from '@/lib/types'

const api = vi.hoisted(() => ({
  createToken: vi.fn(),
  revokeToken: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))

import ClientTokensPanel from '@/components/ClientTokensPanel.vue'

const PENDING: EnrollmentToken = {
  id: 't1',
  state: 'pending',
  created_at: '2026-10-01T10:00:00Z',
  expires_at: '2026-10-04T10:00:00Z',
  created_by: 'admin@seo.example',
  used_at: null,
  used_by_instance_id: null,
  revoked_at: null,
}

function mountPanel(tokens: EnrollmentToken[] = [], loading = false) {
  return mount(ClientTokensPanel, { props: { clientId: 'c1', tokens, loading } })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.createToken.mockResolvedValue({ token: 'svk_enr_secreto' })
  api.revokeToken.mockResolvedValue(undefined)
})

describe('tokens de vinculación', () => {
  it('sin tokens avisa que todavía no se generó ninguno', () => {
    const wrapper = mountPanel([])

    expect(wrapper.text()).toContain('Todavía no se generó ningún token')
  })

  it('no muestra el aviso de vacío mientras carga', () => {
    const wrapper = mountPanel([], true)

    expect(wrapper.text()).not.toContain('Todavía no se generó ningún token')
  })

  it('generar un token lo pide con la vigencia elegida y lo muestra una sola vez', async () => {
    const wrapper = mountPanel()

    await wrapper.get('input[type="number"]').setValue(24)
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Generar token de vinculación')
      ?.trigger('click')
    await flushPromises()

    expect(api.createToken).toHaveBeenCalledWith('c1', 24)
    expect(wrapper.text()).toContain('svk_enr_secreto')
  })

  it('al cerrar el diálogo avisa que hay que recargar y descarta el secreto', async () => {
    const wrapper = mountPanel()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Generar token de vinculación')
      ?.trigger('click')
    await flushPromises()

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Ya lo guardé')
      ?.trigger('click')
    await flushPromises()

    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('svk_enr_secreto')
  })

  it('revocar un token vigente llama al API y avisa el cambio', async () => {
    const wrapper = mountPanel([PENDING])

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Revocar')
      ?.trigger('click')
    await flushPromises()

    expect(api.revokeToken).toHaveBeenCalledWith('t1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('un token usado no ofrece revocar', () => {
    const wrapper = mountPanel([{ ...PENDING, state: 'used' }])

    expect(wrapper.findAll('button').some((b) => b.text() === 'Revocar')).toBe(false)
  })
})
