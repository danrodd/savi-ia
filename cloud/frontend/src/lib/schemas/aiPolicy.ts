import { z } from 'zod'
import type { AiPolicy } from '@/lib/types'

/**
 * Proveedores y topes de IA por cliente. Espejo de `AiPolicy` en
 * `cloud/backend/app/modules/clients/policies.py`: montos entre 0 y 99.999.999 USD con hasta
 * 4 decimales, al menos un proveedor y hasta 500 excepciones.
 */

export const PROVIDERS = [
  { key: 'claude', label: 'Claude' },
  { key: 'gemini', label: 'Gemini' },
  { key: 'openai', label: 'OpenAI' },
] as const
export type ProviderKey = (typeof PROVIDERS)[number]['key']

export const AMOUNT = /^\d{1,8}(\.\d{1,4})?$/
export const AMOUNT_HINT = 'En USD, con hasta 4 decimales (por ejemplo 5 o 12.50).'
const MAX_OVERRIDES = 500

const optionalAmount = z
  .string()
  .trim()
  .refine((value) => value === '' || AMOUNT.test(value), AMOUNT_HINT)

export const aiPolicySchema = z
  .object({
    allowed: z.object({ claude: z.boolean(), gemini: z.boolean(), openai: z.boolean() }),
    userMonthly: optionalAmount,
    caps: z.object({ claude: optionalAmount, gemini: optionalAmount, openai: optionalAmount }),
    overrides: z
      .array(z.object({ user_ref: z.string(), amount: z.string() }))
      .max(MAX_OVERRIDES, `Hasta ${MAX_OVERRIDES} excepciones por cliente.`),
  })
  .superRefine((value, ctx) => {
    if (PROVIDERS.every((p) => !value.allowed[p.key])) {
      ctx.addIssue({
        code: 'custom',
        path: ['allowed'],
        message: 'Dejá al menos un proveedor habilitado.',
      })
    }
  })

export type AiPolicyForm = z.input<typeof aiPolicySchema>

export function toForm(policy: AiPolicy): AiPolicyForm {
  const list = policy.allowed_providers
  return {
    allowed: {
      claude: list === null || list.includes('claude'),
      gemini: list === null || list.includes('gemini'),
      openai: list === null || list.includes('openai'),
    },
    userMonthly: policy.user_monthly_usd ?? '',
    caps: {
      claude: policy.provider_monthly_usd.claude ?? '',
      gemini: policy.provider_monthly_usd.gemini ?? '',
      openai: policy.provider_monthly_usd.openai ?? '',
    },
    overrides: Object.entries(policy.user_overrides).map(([user_ref, amount]) => ({
      user_ref,
      amount,
    })),
  }
}

export function toBody(form: z.output<typeof aiPolicySchema>): AiPolicy {
  const every = PROVIDERS.every((p) => form.allowed[p.key])
  const caps: Record<string, string> = {}
  for (const p of PROVIDERS) {
    if (form.caps[p.key]) caps[p.key] = form.caps[p.key]
  }
  return {
    allowed_providers: every
      ? null
      : PROVIDERS.filter((p) => form.allowed[p.key]).map((p) => p.key),
    user_monthly_usd: form.userMonthly || null,
    provider_monthly_usd: caps,
    user_overrides: Object.fromEntries(form.overrides.map((o) => [o.user_ref, o.amount])),
  }
}
