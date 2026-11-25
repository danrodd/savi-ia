import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({ report: vi.fn(), exportCsv: vi.fn() }))
vi.mock('../services/catalogGapsService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/catalogGapsService')>()),
  catalogGapsService: serviceMock,
}))

import CatalogGapsView from '../views/CatalogGapsView.vue'

const RouterLinkStub = { template: '<a><slot /></a>' }

function mountView() {
  return mount(CatalogGapsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CatalogGapsView', () => {
  it('muestra los totales, las tablas más pedidas y cada pregunta con lo que pasó', async () => {
    serviceMock.report.mockResolvedValue({
      start: '2026-10-27T05:00:00Z',
      end: '2026-11-26T05:00:00Z',
      totals: { free_query: 7, failed_query: 0, query_limit: 1 },
      gaps: [
        {
          question: 'Agrégale también la retención en la fuente de cada compra',
          kinds: ['free_query', 'query_limit'],
          times: 1,
          last_at: '2026-11-25T14:23:29Z',
          tables: ['CuentaPagar.FacturaIndicadorRetencionCompra'],
          conversation_id: 'c1',
        },
      ],
      top_tables: [{ table: 'Contabilidad.PlanContable', times: 3 }],
    })

    const wrapper = mountView()
    await flushPromises()

    expect(serviceMock.report).toHaveBeenCalledWith({ from: undefined, to: undefined })
    const totals = wrapper.find('[data-testid="gaps-totals"]').text()
    expect(totals).toContain('7')
    expect(totals).toContain('Llegó al tope de consultas')
    expect(wrapper.find('[data-testid="gaps-top-tables"]').text()).toContain(
      'Contabilidad.PlanContable',
    )
    const table = wrapper.find('[data-testid="gaps-table"]').text()
    expect(table).toContain('retención en la fuente')
    expect(table).toContain('Resuelta con consulta libre')
    expect(table).toContain('CuentaPagar.FacturaIndicadorRetencionCompra')
  })

  it('consulta el periodo elegido', async () => {
    serviceMock.report.mockResolvedValue({
      start: '',
      end: '',
      totals: { free_query: 0, failed_query: 0, query_limit: 0 },
      gaps: [],
      top_tables: [],
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-testid="gaps-from"]').setValue('2026-11-01')
    await wrapper.find('[data-testid="gaps-to"]').setValue('2026-11-25')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(serviceMock.report).toHaveBeenLastCalledWith({ from: '2026-11-01', to: '2026-11-25' })
    expect(wrapper.find('[data-testid="gaps-empty"]').exists()).toBe(true)
  })
})
