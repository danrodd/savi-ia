import { z } from 'zod'

/**
 * Suscripción y movimientos del cliente. Espejo de las reglas de
 * `cloud/backend/app/modules/clients/subscription.py`; el backend sigue siendo la autoridad.
 */

const MONEY = /^\d{1,8}(\.\d{1,2})?$/
const SIGNED_MONEY = /^-?\d{1,8}(\.\d{1,2})?$/
const MONEY_HINT = 'En USD, con hasta 2 decimales (por ejemplo 120 o 49.90).'
const MAX_NOTE = 500
const MAX_USERS = 100_000

/** Texto opcional: vacío viaja como `null`. */
const optionalText = (max: number, message: string) =>
  z
    .string()
    .trim()
    .max(max, message)
    .transform((value) => value || null)

const optionalDay = z
  .string()
  .trim()
  .refine((value) => value === '' || /^\d{4}-\d{2}-\d{2}$/.test(value), 'Elegí una fecha válida.')
  .transform((value) => value || null)

export const planSchema = z.object({
  plan_name: optionalText(80, 'El nombre del plan admite hasta 80 caracteres.'),
  monthly_fee_usd: z
    .string()
    .trim()
    .refine((value) => value === '' || MONEY.test(value), MONEY_HINT)
    .transform((value) => value || null),
  max_users: z
    .number({ error: 'Tiene que ser un número entero.' })
    .int('Tiene que ser un número entero.')
    .min(1, 'El cupo tiene que ser mayor que cero.')
    .max(MAX_USERS, `El cupo admite hasta ${MAX_USERS.toLocaleString('es-CO')} personas.`)
    .nullable(),
  valid_until: optionalDay,
  notes: optionalText(MAX_NOTE, `Las notas admiten hasta ${MAX_NOTE} caracteres.`),
})

export type PlanInput = z.input<typeof planSchema>

export const ledgerEntrySchema = z
  .object({
    kind: z.enum(['payment', 'adjustment']),
    amount_usd: z.string().trim().min(1, 'Ingresá el monto.'),
    note: z
      .string()
      .trim()
      .min(1, 'Anotá la referencia (por ejemplo, el número de transferencia).')
      .max(MAX_NOTE, `La referencia admite hasta ${MAX_NOTE} caracteres.`),
    extends_until: optionalDay,
  })
  .superRefine((value, ctx) => {
    const amount = value.amount_usd
    if (!amount) return
    if (!SIGNED_MONEY.test(amount)) {
      ctx.addIssue({ code: 'custom', path: ['amount_usd'], message: MONEY_HINT })
    } else if (value.kind === 'payment' && amount.startsWith('-')) {
      ctx.addIssue({
        code: 'custom',
        path: ['amount_usd'],
        message: 'Un pago no puede ser negativo: para descontar, registrá un ajuste.',
      })
    } else if (value.kind === 'payment' && Number(amount) === 0) {
      ctx.addIssue({
        code: 'custom',
        path: ['amount_usd'],
        message: 'Un pago no puede ser de cero.',
      })
    }
  })

export type LedgerEntryForm = z.input<typeof ledgerEntrySchema>
