import { readonly, ref, shallowRef } from 'vue'
import { consoleApi } from '@/lib/api'
import type { Alert } from '@/lib/types'

/**
 * Alertas abiertas (sin reconocer), compartidas por el contador del menú, la campana y los avisos.
 *
 * Cada lectura compara con la anterior: lo que no estaba es "nuevo" y queda en `freshAlerts`
 * para que la consola lo anuncie. La primera lectura solo fija la base, así que entrar a la
 * consola con alertas viejas no dispara una ráfaga de avisos.
 */
const count = ref<number | null>(null)
const items = shallowRef<Alert[]>([])
const fresh = shallowRef<Alert[]>([])
let known: Set<string> | null = null

export const openAlerts = readonly(count)
/** Las alertas abiertas más recientes (hasta 100), de la más nueva a la más vieja. */
export const openAlertList = readonly(items)
/** Las que aparecieron en la última lectura (vacío en la primera). */
export const freshAlerts = readonly(fresh)

/** Relee las alertas. Un fallo deja lo anterior: son ayuda, no bloquean nada. */
export async function refreshOpenAlerts(): Promise<void> {
  // El contador y la lista son independientes: si la lista falla, el contador sigue al día.
  try {
    count.value = (await consoleApi.alertSummary()).open
  } catch {
    // Se reintenta en la próxima navegación o intervalo.
  }
  try {
    const list = await consoleApi.alerts({ status: 'open' })
    const sorted = [...list].sort((a, b) => b.opened_at.localeCompare(a.opened_at))
    items.value = sorted
    fresh.value = known ? sorted.filter((a) => !known?.has(a.id)) : []
    known = new Set(sorted.map((a) => a.id))
  } catch {
    fresh.value = []
  }
}

export function resetOpenAlertsForTests(): void {
  count.value = null
  items.value = []
  fresh.value = []
  known = null
}
