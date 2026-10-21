/**
 * Estado de la actualización automática, consultado en segundo plano.
 *
 * - En reposo consulta cada 15 min y al volver a la pestaña. El backend ya
 *   chequea el servidor cada 6 h: esto solo lee lo que sabe.
 * - Mientras se descarga, consulta cada segundo para la barra de progreso.
 * - Cuando el instalador corre, el backend se cae. Desde ahí consulta
 *   `/health` hasta que responde otra versión, y recarga la página.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { HttpRequestError } from '@/lib/HttpClient'
import { STORAGE_KEYS } from '@/lib/storageKeys'
import { updatesService } from '../services/updatesService'
import type { UpdateStatus } from '../types'
import { isApplying, noticeKind, restartedWithNewVersion, SNOOZE_MS } from '../utils/updateView'

const IDLE_INTERVAL_MS = 15 * 60 * 1000
const ACTIVE_INTERVAL_MS = 1000
const RESTART_INTERVAL_MS = 2000

function readSnooze(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEYS.UPDATE_SNOOZED_UNTIL)
    return raw === null ? null : Number(raw)
  } catch {
    return null
  }
}

function writeSnooze(until: number): void {
  try {
    window.localStorage.setItem(STORAGE_KEYS.UPDATE_SNOOZED_UNTIL, String(until))
  } catch {
    // Sin almacenamiento, "Más tarde" vale solo para esta pestaña.
  }
}

export function useUpdateStatus() {
  const status = ref<UpdateStatus | null>(null)
  const snoozedUntil = ref<number | null>(readSnooze())
  const now = ref(Date.now())
  const applyError = ref<string | null>(null)
  const restarting = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = false

  const kind = computed(() => {
    if (restarting.value) return 'progress' as const
    return noticeKind(status.value, now.value, snoozedUntil.value)
  })

  function schedule(ms: number): void {
    if (stopped) return
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => void refresh(), ms)
  }

  async function waitForRestart(): Promise<void> {
    const previous = status.value?.current_version ?? null
    const version = await updatesService.healthVersion()
    if (restartedWithNewVersion(version, previous)) {
      window.location.reload()
      return
    }
    schedule(RESTART_INTERVAL_MS)
  }

  async function refresh(): Promise<void> {
    now.value = Date.now()
    if (restarting.value) {
      await waitForRestart()
      return
    }
    try {
      status.value = await updatesService.getStatus()
    } catch {
      // Si la instalación ya empezó, el backend caído es lo esperable.
      if (status.value?.phase === 'installing') {
        restarting.value = true
        schedule(RESTART_INTERVAL_MS)
        return
      }
      schedule(IDLE_INTERVAL_MS)
      return
    }
    if (status.value.phase === 'installing') restarting.value = true
    schedule(isApplying(status.value) ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS)
  }

  async function apply(): Promise<void> {
    applyError.value = null
    try {
      status.value = await updatesService.apply()
      schedule(ACTIVE_INTERVAL_MS)
    } catch (error) {
      applyError.value =
        error instanceof HttpRequestError
          ? error.message
          : 'No se pudo iniciar la actualización. Intente de nuevo.'
    }
  }

  function snooze(): void {
    const until = Date.now() + SNOOZE_MS
    snoozedUntil.value = until
    writeSnooze(until)
  }

  function onVisibility(): void {
    if (document.visibilityState === 'visible') void refresh()
  }

  onMounted(() => {
    void refresh()
    document.addEventListener('visibilitychange', onVisibility)
  })

  onUnmounted(() => {
    stopped = true
    if (timer !== null) clearTimeout(timer)
    document.removeEventListener('visibilitychange', onVisibility)
  })

  return { status, kind, applyError, apply, snooze, refresh }
}
