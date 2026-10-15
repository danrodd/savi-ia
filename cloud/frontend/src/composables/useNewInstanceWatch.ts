import { onBeforeUnmount, type Ref, ref } from 'vue'
import { consoleApi } from '@/lib/api'
import type { Instance } from '@/lib/types'

export type WatchState = 'idle' | 'waiting' | 'found' | 'timeout'

interface Options {
  intervalMs?: number
  timeoutMs?: number
}

/**
 * Espera a que una instalación nueva se vincule a un cliente: consulta sus instancias cada
 * pocos segundos y avisa cuando aparece una que no estaba al generar el token.
 *
 * No consulta con la pestaña oculta, se detiene al encontrarla, al agotar el tiempo y al
 * desmontar el componente.
 */
export function useNewInstanceWatch(clientId: () => string, options: Options = {}) {
  const intervalMs = options.intervalMs ?? 5_000
  const timeoutMs = options.timeoutMs ?? 10 * 60_000

  const state = ref<WatchState>('idle')
  const found = ref<Instance | null>(null) as Ref<Instance | null>

  let known: Set<string> | null = null
  let timer: ReturnType<typeof setInterval> | undefined
  let deadline = 0
  let inFlight = false

  /** Las instancias que ya existen: lo que aparezca después es "la nueva". */
  async function snapshot(): Promise<void> {
    try {
      known = new Set((await consoleApi.instances({ client_id: clientId() })).map((i) => i.id))
    } catch {
      // Sin línea base: la primera consulta que funcione la fija.
      known = null
    }
  }

  function clear(): void {
    if (timer !== undefined) clearInterval(timer)
    timer = undefined
  }

  function stop(): void {
    clear()
    document.removeEventListener('visibilitychange', onVisibility)
    if (state.value === 'waiting') state.value = 'idle'
  }

  function finish(next: WatchState): void {
    clear()
    document.removeEventListener('visibilitychange', onVisibility)
    state.value = next
  }

  async function check(): Promise<void> {
    if (state.value !== 'waiting' || inFlight || document.hidden) return
    if (Date.now() >= deadline) {
      finish('timeout')
      return
    }
    inFlight = true
    try {
      const items = await consoleApi.instances({ client_id: clientId() })
      if (state.value !== 'waiting') return
      if (known === null) {
        known = new Set(items.map((i) => i.id))
        return
      }
      const fresh = items.find((i) => !known?.has(i.id))
      if (fresh) {
        found.value = fresh
        finish('found')
      }
    } catch {
      // Un fallo de red no corta la espera: se reintenta en el próximo ciclo.
    } finally {
      inFlight = false
    }
  }

  function onVisibility(): void {
    if (state.value !== 'waiting') return
    if (document.hidden) {
      clear()
      return
    }
    void check()
    clear()
    timer = setInterval(() => void check(), intervalMs)
  }

  /** Empieza a esperar. Llámalo después de `snapshot()`, cuando la persona ya tiene el token. */
  function start(): void {
    clear()
    found.value = null
    state.value = 'waiting'
    deadline = Date.now() + timeoutMs
    document.addEventListener('visibilitychange', onVisibility)
    if (!document.hidden) timer = setInterval(() => void check(), intervalMs)
  }

  function reset(): void {
    stop()
    found.value = null
    state.value = 'idle'
  }

  onBeforeUnmount(stop)

  return { state, found, snapshot, start, stop, reset }
}
