/**
 * Polling automático de la versión de módulos.
 *
 * - Cada `intervalMs` (default 5 min) consulta `/auth/me/modules-version`.
 * - Cuando la pestaña vuelve a primer plano (visibilitychange), dispara
 *   un check inmediato — no espera al próximo tick.
 * - Si la versión cambió, el store recarga el bootstrap completo y la
 *   UI se actualiza reactivamente (sin reload manual).
 *
 * Se monta una sola vez en el root (App.vue o equivalente).
 */
import { onMounted, onUnmounted } from 'vue'

import { usePermisosStore } from '../stores/permisosStore'

const DEFAULT_INTERVAL_MS = 5 * 60 * 1000

export function usePermisosPolling(intervalMs: number = DEFAULT_INTERVAL_MS): void {
  const store = usePermisosStore()
  let timer: ReturnType<typeof setInterval> | null = null

  const tick = (): void => {
    void store.verificarVersion()
  }

  const onVisibility = (): void => {
    if (typeof document !== 'undefined' && document.visibilityState === 'visible') tick()
  }

  onMounted(() => {
    timer = setInterval(tick, intervalMs)
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibility)
    }
  })

  onUnmounted(() => {
    if (timer !== null) clearInterval(timer)
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibility)
    }
  })
}
