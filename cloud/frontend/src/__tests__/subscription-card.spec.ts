import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LedgerEntry, Subscription } from '@/lib/types'

const api = vi.hoisted(() => ({
  subscription: vi.fn(),
  setSubscription: vi.fn(),
  ledger: vi.fn(),
  recordLedgerEntry: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))

import SubscriptionCard from '@/components/SubscriptionCard.vue'

const PLAN: Subscription = {
  plan_name: 'Equipo',
  monthly_fee_usd: '120.00',
  max_users: 10,
  valid_until: '2026-01-31',
  notes: null,
  status: 'active',
  days_left: 30,
}

const ENTRY: LedgerEntry = {
  id: 'e1',
  kind: 'payment',
  amount_usd: '120.00',
  note: 'Transferencia 4412',
  extends_until: '2026-01-31',
  created_by: 'comercial@seo.example',
  created_at: '2026-01-01T10:00:00Z',
}

async function mountCard() {
  const wrapper = mount(SubscriptionCard, { props: { clientId: 'c1' } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  api.subscription.mockResolvedValue(PLAN)
  api.ledger.mockResolvedValue([ENTRY])
  api.setSubscription.mockResolvedValue({ ...PLAN, plan_name: 'Pro' })
  api.recordLedgerEntry.mockResolvedValue(ENTRY)
})

describe('suscripción del cliente', () => {
  it('muestra el plan, la vigencia y los movimientos', async () => {
    const wrapper = await mountCard()

    expect(wrapper.get('[data-test="billing-status"]').text()).toContain('Vigente')
    expect(wrapper.get('[data-test="billing-status"]').text()).toContain('31/01/2026')
    expect((wrapper.get('[data-test="plan-name"]').element as HTMLInputElement).value).toBe(
      'Equipo',
    )
    expect(wrapper.findAll('[data-test="ledger-row"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Transferencia 4412')
  })

  it('sin movimientos avisa que todavía no hay ninguno', async () => {
    api.ledger.mockResolvedValue([])

    const wrapper = await mountCard()

    expect(wrapper.find('[data-test="ledger-empty"]').exists()).toBe(true)
  })

  it('una vencida se marca como tal', async () => {
    api.subscription.mockResolvedValue({ ...PLAN, status: 'expired', days_left: -3 })

    const wrapper = await mountCard()

    expect(wrapper.get('[data-test="billing-status"]').text()).toContain('Vencida')
  })

  it('guardar el plan manda los campos limpios', async () => {
    const wrapper = await mountCard()

    await wrapper.get('[data-test="plan-name"]').setValue('Pro')
    await wrapper.get('[data-test="plan-fee"]').setValue('199.90')
    await wrapper.get('[data-test="plan-users"]').setValue('25')
    await wrapper.get('[data-test="plan-save"]').trigger('click')
    await flushPromises()

    expect(api.setSubscription).toHaveBeenCalledWith('c1', {
      plan_name: 'Pro',
      monthly_fee_usd: '199.90',
      max_users: 25,
      valid_until: '2026-01-31',
      notes: null,
    })
  })

  it('no manda una cuota con formato inválido', async () => {
    const wrapper = await mountCard()

    await wrapper.get('[data-test="plan-fee"]').setValue('cien')
    await wrapper.get('[data-test="plan-save"]').trigger('click')
    await flushPromises()

    expect(api.setSubscription).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="billing-error"]').text()).toContain('USD')
  })

  it('registrar un pago lo manda y recarga el historial', async () => {
    const wrapper = await mountCard()

    await wrapper.get('[data-test="entry-amount"]').setValue('120')
    await wrapper.get('[data-test="entry-note"]').setValue('Transferencia 4413')
    await wrapper.get('[data-test="entry-until"]').setValue('2026-02-28')
    await wrapper.get('[data-test="entry-save"]').trigger('click')
    await flushPromises()

    expect(api.recordLedgerEntry).toHaveBeenCalledWith('c1', {
      kind: 'payment',
      amount_usd: '120',
      note: 'Transferencia 4413',
      extends_until: '2026-02-28',
    })
    expect(api.ledger).toHaveBeenCalledTimes(2)
  })

  it('un pago sin referencia no se registra', async () => {
    const wrapper = await mountCard()

    await wrapper.get('[data-test="entry-amount"]').setValue('50')
    await wrapper.get('[data-test="entry-save"]').trigger('click')
    await flushPromises()

    expect(api.recordLedgerEntry).not.toHaveBeenCalled()
  })

  it('un pago negativo se rechaza y sugiere un ajuste', async () => {
    const wrapper = await mountCard()

    await wrapper.get('[data-test="entry-amount"]').setValue('-10')
    await wrapper.get('[data-test="entry-note"]').setValue('x')
    await wrapper.get('[data-test="entry-save"]').trigger('click')
    await flushPromises()

    expect(api.recordLedgerEntry).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="billing-error"]').text()).toContain('ajuste')
  })
})
