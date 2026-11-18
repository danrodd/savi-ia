import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('../services/failedTurnsService', () => ({ failedTurnsService: serviceMock }))

import FailedTurnsView from '../views/FailedTurnsView.vue'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('FailedTurnsView', () => {
  it('lista cada turno con su causa y su código de soporte', async () => {
    serviceMock.list.mockResolvedValue([
      {
        message_id: 'm1',
        conversation_id: 'c1',
        conversation_title: 'Productos sin movimiento',
        user_id: 7,
        created_at: '2026-11-11T21:30:00Z',
        error_code: 'provider_busy',
        error_message: 'El servicio de inteligencia artificial está saturado en este momento.',
        support_code: 'A1B2C3D4',
        provider: 'openai',
        model: 'gpt-6-luna',
        erp_queries: 2,
      },
    ])

    const wrapper = mount(FailedTurnsView)
    await flushPromises()

    const table = wrapper.find('[data-testid="failed-turns-table"]')
    expect(table.exists()).toBe(true)
    expect(table.text()).toContain('Proveedor saturado')
    expect(table.text()).toContain('A1B2C3D4')
    expect(table.text()).toContain('openai · gpt-6-luna')
  })

  it('sin turnos fallidos lo dice', async () => {
    serviceMock.list.mockResolvedValue([])

    const wrapper = mount(FailedTurnsView)
    await flushPromises()

    expect(wrapper.find('[data-testid="failed-turns-empty"]').exists()).toBe(true)
  })
})
