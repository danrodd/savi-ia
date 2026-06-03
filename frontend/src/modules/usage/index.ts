/**
 * Contrato público del módulo `usage`. Importá SIEMPRE desde
 * `@/modules/usage`, nunca desde subcarpetas internas.
 */

export type { RangeDays } from './stores/usageStore'
export { useUsageStore } from './stores/usageStore'
export type {
  DailyUsage,
  SystemUsageReport,
  UsageTotals,
  UserUsage,
  UserUsageReport,
} from './types'
