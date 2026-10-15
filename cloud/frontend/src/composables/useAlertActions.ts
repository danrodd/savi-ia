import { toast } from '@savi/ui'
import { ref } from 'vue'
import { consoleApi } from '@/lib/api'
import type { Alert, BulkAlertResult } from '@/lib/types'
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
  /** Resolución masiva en curso: los ids que se van a resolver con una misma nota. */
  const resolvingMany = ref<string[] | null>(null)
  const bulkBusy = ref(false)

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
    resolvingMany.value = null
    note.value = ''
  }

  function closeResolve(): void {
    resolving.value = null
    resolvingMany.value = null
  }

  function bulkToast(done: string, result: BulkAlertResult): void {
    const alertas = (n: number) => (n === 1 ? '1 alerta' : `${n} alertas`)
    if (result.changed === 0) {
      toast.info('No cambió ninguna alerta', {
        description: `${alertas(result.skipped)} ya estaban en ese estado o se resolvieron antes.`,
      })
      return
    }
    toast.success(`${alertas(result.changed)} ${done}`, {
      description:
        result.skipped > 0
          ? `${alertas(result.skipped)} se omitieron porque ya no estaban pendientes.`
          : undefined,
    })
  }

  async function acknowledgeMany(ids: string[]): Promise<boolean> {
    if (ids.length === 0) return false
    bulkBusy.value = true
    try {
      const result = await consoleApi.acknowledgeAlerts(ids)
      bulkToast(result.changed === 1 ? 'reconocida' : 'reconocidas', result)
      await changed()
      return true
    } catch (e) {
      toast.error('No se pudieron reconocer las alertas', { description: errorMessage(e) })
      return false
    } finally {
      bulkBusy.value = false
    }
  }

  function openResolveMany(ids: string[]): void {
    if (ids.length === 0) return
    resolving.value = null
    resolvingMany.value = [...ids]
    note.value = ''
  }

  async function resolveMany(): Promise<void> {
    const ids = resolvingMany.value
    if (!ids) return
    resolveBusy.value = true
    try {
      const result = await consoleApi.resolveAlerts(ids, note.value.trim())
      bulkToast(result.changed === 1 ? 'resuelta' : 'resueltas', result)
      resolvingMany.value = null
      await changed()
    } catch (e) {
      toast.error('No se pudieron resolver las alertas', { description: errorMessage(e) })
    } finally {
      resolveBusy.value = false
    }
  }

  async function resolve(): Promise<void> {
    if (resolvingMany.value) return resolveMany()
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

  return {
    busyId,
    resolving,
    resolvingMany,
    note,
    resolveBusy,
    bulkBusy,
    canManage,
    acknowledge,
    acknowledgeMany,
    openResolve,
    openResolveMany,
    closeResolve,
    resolve,
  }
}

export type AlertActions = ReturnType<typeof useAlertActions>
