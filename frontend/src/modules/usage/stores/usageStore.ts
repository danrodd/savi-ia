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
import type {
  ConversationUsage,
  SystemUsageReport,
  UsageKpis,
  UsageQuery,
  UserUsageReport,
} from '../types'

export type RangeDays = 7 | 30 | 90

// Tope de filas del detalle por conversación que pedimos al backend.
const CONVERSATIONS_LIMIT = 500

export const useUsageStore = defineStore('usage', () => {
  const rangeDays = ref<RangeDays>(30)

  const mine = ref<UserUsageReport | null>(null)
  const loadingMine = ref(false)
  const errorMine = ref<string | null>(null)

  const system = ref<SystemUsageReport | null>(null)
  const loadingSystem = ref(false)
  const errorSystem = ref<string | null>(null)

  const kpis = ref<UsageKpis | null>(null)
  const loadingKpis = ref(false)
  const errorKpis = ref<string | null>(null)

  const conversations = ref<ConversationUsage[]>([])
  const loadingConversations = ref(false)
  const errorConversations = ref<string | null>(null)

  const usdToCopRate = computed<number>(
    () =>
      kpis.value?.usd_to_cop_rate ??
      mine.value?.usd_to_cop_rate ??
      system.value?.usd_to_cop_rate ??
      0,
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

  async function loadKpis(): Promise<void> {
    loadingKpis.value = true
    errorKpis.value = null
    try {
      kpis.value = await usageService.kpis(periodQuery())
    } catch (e) {
      errorKpis.value = (e as Error).message || 'No se pudieron cargar los KPIs.'
    } finally {
      loadingKpis.value = false
    }
  }

  async function loadConversations(): Promise<void> {
    loadingConversations.value = true
    errorConversations.value = null
    try {
      conversations.value = await usageService.conversations({
        ...periodQuery(),
        limit: CONVERSATIONS_LIMIT,
      })
    } catch (e) {
      errorConversations.value =
        (e as Error).message || 'No se pudo cargar el detalle por conversación.'
    } finally {
      loadingConversations.value = false
    }
  }

  /** Cambia el rango y recarga lo que ya estaba cargado. */
  async function setRange(days: RangeDays): Promise<void> {
    if (days === rangeDays.value) return
    rangeDays.value = days
    const tasks: Promise<void>[] = []
    if (mine.value || loadingMine.value) tasks.push(loadMine())
    if (system.value || loadingSystem.value) tasks.push(loadSystem())
    if (kpis.value || loadingKpis.value) tasks.push(loadKpis())
    if (conversations.value.length > 0 || loadingConversations.value) {
      tasks.push(loadConversations())
    }
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
    kpis,
    loadingKpis,
    errorKpis,
    conversations,
    loadingConversations,
    errorConversations,
    usdToCopRate,
    loadMine,
    loadSystem,
    loadKpis,
    loadConversations,
    setRange,
  }
})
