import { toast } from '@savi/ui'
import { ref } from 'vue'
import { consoleApi } from '@/lib/api'
import type { Alert } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'
import { refreshOpenAlerts } from './useOpenAlerts'

/**
 * Reconocer y resolver alertas, compartido por la pantalla de alertas y la pestaña del cliente.
 * `onChanged` recarga la lista de quien lo usa; el contador del menú se actualiza solo.
 */
export function useAlertActions(onChanged: () => Promise<void> | void) {
  const auth = useAuthStore()

  const busyId = ref<string | null>(null)
  const resolving = ref<Alert | null>(null)
  const note = ref('')
  const resolveBusy = ref(false)

  function canManage(alert: Alert): boolean {
    return auth.can('alerts.manage') && alert.status !== 'resolved'
  }

  async function changed(): Promise<void> {
    void refreshOpenAlerts()
    await onChanged()
  }

  async function acknowledge(alert: Alert): Promise<void> {
    busyId.value = alert.id
    try {
      await consoleApi.acknowledgeAlert(alert.id)
      toast.success('Alerta reconocida')
      await changed()
    } catch (e) {
      toast.error('No se pudo reconocer la alerta', { description: errorMessage(e) })
    } finally {
      busyId.value = null
    }
  }

  function openResolve(alert: Alert): void {
    resolving.value = alert
    note.value = ''
  }

  async function resolve(): Promise<void> {
    const alert = resolving.value
    if (!alert) return
    resolveBusy.value = true
    try {
      await consoleApi.resolveAlert(alert.id, note.value.trim())
      toast.success('Alerta resuelta')
      resolving.value = null
      await changed()
    } catch (e) {
      toast.error('No se pudo resolver la alerta', { description: errorMessage(e) })
    } finally {
      resolveBusy.value = false
    }
  }

  return { busyId, resolving, note, resolveBusy, canManage, acknowledge, openResolve, resolve }
}

export type AlertActions = ReturnType<typeof useAlertActions>
