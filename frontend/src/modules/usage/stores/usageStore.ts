/**
 * Pinia store del consumo.
 *
 * Sigue el patrón del proyecto: el store ES la capa de datos (no hay
 * vue-query). Mantiene el reporte propio y el global por separado, cada
 * uno con su loading/error, y un rango temporal compartido (7/30/90 días)
 * que se traduce a `start`/`end` ISO al consultar.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { usageService } from '../services/usageService'
import type { SystemUsageReport, UsageQuery, UserUsageReport } from '../types'

export type RangeDays = 7 | 30 | 90

export const useUsageStore = defineStore('usage', () => {
  const rangeDays = ref<RangeDays>(30)

  const mine = ref<UserUsageReport | null>(null)
  const loadingMine = ref(false)
  const errorMine = ref<string | null>(null)

  const system = ref<SystemUsageReport | null>(null)
  const loadingSystem = ref(false)
  const errorSystem = ref<string | null>(null)

  const usdToCopRate = computed<number>(
    () => mine.value?.usd_to_cop_rate ?? system.value?.usd_to_cop_rate ?? 0,
  )

  function periodQuery(): UsageQuery {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - rangeDays.value)
    return { start: start.toISOString(), end: end.toISOString() }
  }

  async function loadMine(): Promise<void> {
    loadingMine.value = true
    errorMine.value = null
    try {
      mine.value = await usageService.me(periodQuery())
    } catch (e) {
      errorMine.value = (e as Error).message || 'No se pudo cargar tu consumo.'
    } finally {
      loadingMine.value = false
    }
  }

  async function loadSystem(): Promise<void> {
    loadingSystem.value = true
    errorSystem.value = null
    try {
      system.value = await usageService.system(periodQuery())
    } catch (e) {
      errorSystem.value = (e as Error).message || 'No se pudo cargar el consumo global.'
    } finally {
      loadingSystem.value = false
    }
  }

  /** Cambia el rango y recarga lo que ya estaba cargado. */
  async function setRange(days: RangeDays): Promise<void> {
    if (days === rangeDays.value) return
    rangeDays.value = days
    const tasks: Promise<void>[] = []
    if (mine.value || loadingMine.value) tasks.push(loadMine())
    if (system.value || loadingSystem.value) tasks.push(loadSystem())
    await Promise.all(tasks)
  }

  return {
    rangeDays,
    mine,
    loadingMine,
    errorMine,
    system,
    loadingSystem,
    errorSystem,
    usdToCopRate,
    loadMine,
    loadSystem,
    setRange,
  }
})
