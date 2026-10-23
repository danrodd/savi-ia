/**
 * Estado de la actualización automática, consultado en segundo plano.
 *
 * - En reposo consulta cada 15 min y al volver a la pestaña. El backend ya
 *   chequea el servidor cada 6 h: esto solo lee lo que sabe.
 * - Mientras se descarga, consulta cada segundo para la barra de progreso.
 * - Cuando el instalador corre, el backend se cae. Desde ahí consulta
 *   `/health` hasta que responde otra versión, y recarga la página.
 * - Si SAVI vuelve con la misma versión, la instalación no se aplicó: se deja
 *   de esperar y se muestra el resultado. Si el instalador tarda demasiado,
 *   se avisa en lugar de esperar para siempre.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { HttpRequestError } from '@/lib/HttpClient'
import { STORAGE_KEYS } from '@/lib/storageKeys'
import { updatesService } from '../services/updatesService'
import type { UpdateStatus } from '../types'
import {
  installStalled,
  isApplying,
  noticeKind,
  restartedWithNewVersion,
  resultNotice,
  SNOOZE_MS,
} from '../utils/updateView'

const IDLE_INTERVAL_MS = 15 * 60 * 1000
const ACTIVE_INTERVAL_MS = 1000
const RESTART_INTERVAL_MS = 2000

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Sin almacenamiento, el valor vale solo para esta pestaña.
  }
}

function readSnooze(): number | null {
  const raw = readStored(STORAGE_KEYS.UPDATE_SNOOZED_UNTIL)
  return raw === null ? null : Number(raw)
}

export function useUpdateStatus() {
  const status = ref<UpdateStatus | null>(null)
  const snoozedUntil = ref<number | null>(readSnooze())
  const seenResultId = ref<string | null>(readStored(STORAGE_KEYS.UPDATE_RESULT_SEEN))
  const now = ref(Date.now())
  const applyError = ref<string | null>(null)
  const restarting = ref(false)
  // Desde cuándo se espera que SAVI vuelva; sirve para avisar si tarda demasiado.
  const waitingSince = ref<number | null>(null)
  // La persona dejó de esperar: no se vuelve a entrar en la espera hasta que SAVI responda.
  const abandoned = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = false

  const kind = computed(() => {
    if (restarting.value) return 'progress' as const
    return noticeKind(status.value, now.value, snoozedUntil.value)
  })

  const stalled = computed(() => restarting.value && installStalled(waitingSince.value, now.value))
  const result = computed(() => resultNotice(status.value, seenResultId.value))

  function schedule(ms: number): void {
    if (stopped) return
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => void refresh(), ms)
  }

  function startWaiting(): void {
    restarting.value = true
    if (waitingSince.value === null) waitingSince.value = Date.now()
  }

  function stopWaiting(): void {
    restarting.value = false
    waitingSince.value = null
  }

  async function waitForRestart(): Promise<void> {
    const previous = status.value?.current_version ?? null
    const version = await updatesService.healthVersion()
    if (restartedWithNewVersion(version, previous)) {
      window.location.reload()
      return
    }
    if (version !== null) {
      // Responde la misma versión: o el instalador sigue (por ejemplo, esperando
      // el permiso de administrador) o SAVI volvió sin haberse actualizado.
      try {
        status.value = await updatesService.getStatus()
        if (status.value.phase !== 'installing') {
          stopWaiting()
          schedule(isApplying(status.value) ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS)
          return
        }
      } catch {
        // Sigue esperando: la sesión puede no estar lista todavía.
      }
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
      abandoned.value = false
    } catch {
      // Si la instalación ya empezó, el backend caído es lo esperable.
      if (status.value?.phase === 'installing' && !abandoned.value) {
        startWaiting()
        schedule(RESTART_INTERVAL_MS)
        return
      }
      schedule(IDLE_INTERVAL_MS)
      return
    }
    if (status.value.phase === 'installing') startWaiting()
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
    writeStored(STORAGE_KEYS.UPDATE_SNOOZED_UNTIL, String(until))
  }

  /** Cierra el aviso del resultado: no vuelve a salir para ese intento. */
  function dismissResult(): void {
    const attemptId = result.value?.attemptId
    if (attemptId === undefined) return
    seenResultId.value = attemptId
    writeStored(STORAGE_KEYS.UPDATE_RESULT_SEEN, attemptId)
  }

  /** La persona deja de esperar a que SAVI vuelva (cuando tarda demasiado). */
  function giveUpWaiting(): void {
    abandoned.value = true
    stopWaiting()
    // El estado guardado dice "instalando": sin esto el diálogo de progreso seguiría ahí.
    if (status.value !== null) status.value = { ...status.value, phase: 'idle' }
    schedule(IDLE_INTERVAL_MS)
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

  return {
    status,
    kind,
    applyError,
    stalled,
    result,
    apply,
    snooze,
    dismissResult,
    giveUpWaiting,
    refresh,
  }
}
