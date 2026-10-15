import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LedgerEntry, Subscription } from '@/lib/types'

const api = vi.hoisted(() => ({
  subscription: vi.fn(),
  setSubscription: vi.fn(),
  ledger: vi.fn(),
  recordLedgerEntry: vi.fn(),
}))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))

vi.mock('@/lib/api', () => ({ consoleApi: api, authApi: {} }))
vi.mock('@savi/ui', async (original) => ({ ...(await original<object>()), toast }))

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

/** El `data-test` va en el contenedor del campo: el control es el input de adentro. */
function field(wrapper: VueWrapper, name: string) {
  return wrapper.get(
    `[data-test="${name}"] input, [data-test="${name}"] select, [data-test="${name}"] textarea`,
  )
}

/** Envía el formulario que contiene el botón (como lo haría Enter o el clic en submit). */
async function submit(wrapper: VueWrapper, button: string) {
  const form = wrapper.findAll('form').find((f) => f.find(`[data-test="${button}"]`).exists())
  await form?.trigger('submit')
  await flushPromises()
}

/** Registrar pide confirmación: acepta el diálogo. */
async function confirm(wrapper: VueWrapper) {
  await wrapper.get('[data-test="confirm-accept"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  api.subscription.mockResolvedValue(PLAN)
  api.ledger.mockResolvedValue([ENTRY])
  api.setSubscription.mockResolvedValue({ ...PLAN, plan_name: 'Pro' })
  api.recordLedgerEntry.mockResolvedValue(ENTRY)
})

describe('suscripción del cliente', () => {
  it('muestra el estado, la vigencia y los movimientos', async () => {
    const wrapper = await mountCard()

    expect(wrapper.get('[data-test="billing-status"]').text()).toContain('Vigente')
    expect(wrapper.get('[data-test="billing-status"]').text()).toContain('31/01/2026')
    expect((field(wrapper, 'plan-name').element as HTMLInputElement).value).toBe('Equipo')
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
    expect(wrapper.get('[data-test="billing-status"]').text()).toContain('Venció hace 3 días')
  })

  it('guardar el plan manda los campos limpios y confirma', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'plan-name').setValue('Pro')
    await field(wrapper, 'plan-fee').setValue(' 199.90 ')
    await field(wrapper, 'plan-users').setValue('25')
    await submit(wrapper, 'plan-save')

    expect(api.setSubscription).toHaveBeenCalledWith('c1', {
      plan_name: 'Pro',
      monthly_fee_usd: '199.90',
      max_users: 25,
      valid_until: '2026-01-31',
      notes: null,
    })
    expect(toast.success).toHaveBeenCalledWith('Plan guardado')
  })

  it('sin cambios no deja guardar', async () => {
    const wrapper = await mountCard()

    expect(wrapper.get('[data-test="plan-save"]').attributes('disabled')).toBeDefined()
  })

  it('no manda una cuota con formato inválido y marca el campo', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'plan-fee').setValue('cien')
    await submit(wrapper, 'plan-save')

    expect(api.setSubscription).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="plan-fee"]').text()).toContain('USD')
  })

  it('registrar un pago lo manda, confirma y recarga el historial', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'entry-amount').setValue('120')
    await field(wrapper, 'entry-note').setValue('Transferencia 4413')
    await field(wrapper, 'entry-until').setValue('2026-02-28')
    await submit(wrapper, 'entry-save')
    await confirm(wrapper)

    expect(api.recordLedgerEntry).toHaveBeenCalledWith('c1', {
      kind: 'payment',
      amount_usd: '120',
      note: 'Transferencia 4413',
      extends_until: '2026-02-28',
    })
    expect(toast.success).toHaveBeenCalledWith('Pago registrado')
    expect(api.ledger).toHaveBeenCalledTimes(2)
  })

  it('antes de registrar pide confirmar y resume tipo, monto, referencia y nueva vigencia', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'entry-amount').setValue('120')
    await field(wrapper, 'entry-note').setValue('Transferencia 4413')
    await field(wrapper, 'entry-until').setValue('2026-02-28')
    await submit(wrapper, 'entry-save')

    expect(api.recordLedgerEntry).not.toHaveBeenCalled()
    const text = wrapper.get('[role="dialog"]').text()
    expect(text).toContain('Registrar el pago')
    expect(text).toContain('Pago recibido')
    expect(text).toContain('Transferencia 4413')
    expect(text).toContain('del 31/01/2026 al 28/02/2026')
  })

  it('cancelar la confirmación no registra nada y conserva el formulario', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'entry-amount').setValue('120')
    await field(wrapper, 'entry-note').setValue('Transferencia 4413')
    await submit(wrapper, 'entry-save')
    await wrapper.get('[data-test="confirm-cancel"]').trigger('click')
    await flushPromises()

    expect(api.recordLedgerEntry).not.toHaveBeenCalled()
    expect((field(wrapper, 'entry-note').element as HTMLInputElement).value).toBe(
      'Transferencia 4413',
    )
  })

  it('registrar un movimiento no descarta las ediciones sin guardar del plan', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'plan-name').setValue('Pro')
    await field(wrapper, 'entry-amount').setValue('120')
    await field(wrapper, 'entry-note').setValue('Transferencia 4413')
    await submit(wrapper, 'entry-save')
    await confirm(wrapper)

    expect(api.recordLedgerEntry).toHaveBeenCalled()
    expect(api.ledger).toHaveBeenCalledTimes(2)
    expect((field(wrapper, 'plan-name').element as HTMLInputElement).value).toBe('Pro')
    expect(wrapper.get('[data-test="plan-save"]').attributes('disabled')).toBeUndefined()
  })

  it('si el pago extendió la vigencia y el plan no se tocó, el formulario la acompaña', async () => {
    const wrapper = await mountCard()
    api.subscription.mockResolvedValue({ ...PLAN, valid_until: '2026-02-28' })

    await field(wrapper, 'plan-name').setValue('Pro')
    await field(wrapper, 'entry-amount').setValue('120')
    await field(wrapper, 'entry-note').setValue('Transferencia 4413')
    await submit(wrapper, 'entry-save')
    await confirm(wrapper)

    expect((field(wrapper, 'plan-valid-until').element as HTMLInputElement).value).toBe(
      '2026-02-28',
    )
    expect((field(wrapper, 'plan-name').element as HTMLInputElement).value).toBe('Pro')
  })

  it('un pago sin referencia no se registra y marca el campo', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'entry-amount').setValue('50')
    await submit(wrapper, 'entry-save')

    expect(api.recordLedgerEntry).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="entry-note"]').text()).toContain('referencia')
  })

  it('un pago negativo se rechaza y sugiere un ajuste', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'entry-amount').setValue('-10')
    await field(wrapper, 'entry-note').setValue('x')
    await submit(wrapper, 'entry-save')

    expect(api.recordLedgerEntry).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="entry-amount"]').text()).toContain('ajuste')
  })

  it('un ajuste sí puede ser negativo', async () => {
    const wrapper = await mountCard()

    await field(wrapper, 'entry-kind').setValue('adjustment')
    await field(wrapper, 'entry-amount').setValue('-10')
    await field(wrapper, 'entry-note').setValue('Cortesía')
    await submit(wrapper, 'entry-save')
    await confirm(wrapper)

    expect(api.recordLedgerEntry).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({ kind: 'adjustment', amount_usd: '-10' }),
    )
  })

  it('si el servidor rechaza, avisa con un toast de error', async () => {
    api.setSubscription.mockRejectedValue(new Error('El monto está fuera de rango.'))
    const wrapper = await mountCard()

    await field(wrapper, 'plan-name').setValue('Pro')
    await submit(wrapper, 'plan-save')

    expect(toast.error).toHaveBeenCalledWith('No se pudo guardar el plan', {
      description: 'El monto está fuera de rango.',
    })
  })
})
