import { readonly, ref } from 'vue'
import { consoleApi } from '@/lib/api'

/** Alertas abiertas (sin reconocer), para el contador del menú. `null` hasta la primera lectura. */
const count = ref<number | null>(null)

export const openAlerts = readonly(count)

/** Relee el contador. Un fallo deja el valor anterior: el contador es ayuda, no bloquea nada. */
export async function refreshOpenAlerts(): Promise<void> {
  try {
    count.value = (await consoleApi.alertSummary()).open
  } catch {
    // Se reintenta en la próxima navegación o intervalo.
  }
}

export function resetOpenAlertsForTests(): void {
  count.value = null
}
