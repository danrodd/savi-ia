import { z } from 'zod'
import type { AccessPolicy } from '@/lib/types'
import { AMOUNT, AMOUNT_HINT } from './aiPolicy'

/**
 * Bases por persona y grupos. Espejo de `AccessPolicy` en
 * `cloud/backend/app/modules/clients/policies.py`; el tope de un grupo usa el mismo formato
 * que los topes de IA.
 */

export const accessPolicySchema = z.object({
  limitDefault: z.boolean(),
  defaultDbs: z.array(z.string()),
  rules: z.array(z.object({ user_ref: z.string(), databases: z.array(z.string()) })),
  groups: z.array(
    z.object({
      id: z.string().nullable(),
      name: z.string(),
      members: z.array(z.string()),
      databases: z.array(z.string()),
      cap: z
        .string()
        .trim()
        .refine((value) => value === '' || AMOUNT.test(value), AMOUNT_HINT),
    }),
  ),
})

export type AccessPolicyForm = z.input<typeof accessPolicySchema>

export function toForm(policy: AccessPolicy): AccessPolicyForm {
  return {
    limitDefault: policy.default_databases !== null,
    defaultDbs: [...(policy.default_databases ?? [])],
    rules: Object.entries(policy.user_databases).map(([user_ref, dbs]) => ({
      user_ref,
      databases: [...dbs],
    })),
    groups: policy.groups.map((g) => ({
      id: g.id,
      name: g.name,
      members: [...g.members],
      databases: [...g.databases],
      cap: g.user_monthly_usd ?? '',
    })),
  }
}

export function toBody(form: z.output<typeof accessPolicySchema>): AccessPolicy {
  return {
    default_databases: form.limitDefault ? [...form.defaultDbs] : null,
    user_databases: Object.fromEntries(form.rules.map((r) => [r.user_ref, [...r.databases]])),
    groups: form.groups.map((g) => ({
      id: g.id,
      name: g.name,
      members: [...g.members],
      databases: [...g.databases],
      user_monthly_usd: g.cap || null,
    })),
  }
}
