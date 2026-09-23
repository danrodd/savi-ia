/**
 * Pinia store del consumo.
 *
 * Sigue el patrón del proyecto: el store ES la capa de datos (no hay
 * vue-query). Mantiene el reporte propio y el global por separado, cada
 * uno con su loading/error, y un rango temporal + selección de
 * proveedores compartidos que se traducen a `from`/`to` (fecha, no
 * instante) al consultar — el backend corta el día en su zona de
 * reporte, así "Hoy" y "Ayer" no mezclan turnos de la noche anterior.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { usageService } from '../services/usageService'
import type {
  ConversationUsage,
  SystemUsageReport,
  UsageKpis,
  UsageProviderKind,
  UsageQuery,
  UserUsageReport,
} from '../types'
import { presetToRange, type RangePreset, toLocalIsoDate } from '../utils/dateRange'

export type { RangePreset }

// Tope de filas del detalle por conversación que pedimos al backend.
const CONVERSATIONS_LIMIT = 500

export const useUsageStore = defineStore('usage', () => {
  const preset = ref<RangePreset>(30)
  const customFrom = ref<string>(toLocalIsoDate(new Date()))
  const customTo = ref<string>(toLocalIsoDate(new Date()))
  const providers = ref<UsageProviderKind[]>([])
  // Bases CONSULTADAS (a qué cliente se atendió). Vacío = todas.
  const databases = ref<string[]>([])
  const model = ref('')

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

  function dateRange(): { from: string; to: string } {
    return presetToRange(preset.value, { from: customFrom.value, to: customTo.value })
  }

  function periodQuery(): UsageQuery {
    const { from, to } = dateRange()
    return {
      from,
      to,
      provider: providers.value.length > 0 ? providers.value : undefined,
      model: model.value.trim() ? [model.value.trim()] : undefined,
      database: databases.value.length > 0 ? databases.value : undefined,
    }
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

  async function reloadLoadedReports(): Promise<void> {
    const tasks: Promise<void>[] = []
    if (mine.value || loadingMine.value) tasks.push(loadMine())
    if (system.value || loadingSystem.value) tasks.push(loadSystem())
    if (kpis.value || loadingKpis.value) tasks.push(loadKpis())
    if (conversations.value.length > 0 || loadingConversations.value) {
      tasks.push(loadConversations())
    }
    await Promise.all(tasks)
  }

  /** Cambia el preset de rango y recarga lo que ya estaba cargado. */
  async function setPreset(next: RangePreset): Promise<void> {
    if (next === preset.value) return
    preset.value = next
    await reloadLoadedReports()
  }

  /** Rango personalizado explícito (ambas fechas AAAA-MM-DD). Cambia el
   * preset a 'custom' si todavía no lo estaba. */
  async function setCustomRange(from: string, to: string): Promise<void> {
    customFrom.value = from
    customTo.value = to
    preset.value = 'custom'
    await reloadLoadedReports()
  }

  /** Selección múltiple de proveedores. Vacío = todos. */
  async function setProviders(next: UsageProviderKind[]): Promise<void> {
    providers.value = next
    await reloadLoadedReports()
  }

  /** Selección múltiple de clientes (base consultada). Vacío = todos. */
  async function setDatabases(next: string[]): Promise<void> {
    databases.value = next
    await reloadLoadedReports()
  }

  async function setModel(value: string): Promise<void> {
    const next = value.trim()
    if (next === model.value) return
    model.value = next
    await reloadLoadedReports()
  }

  return {
    preset,
    customFrom,
    customTo,
    providers,
    databases,
    model,
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
    dateRange,
    loadMine,
    loadSystem,
    loadKpis,
    loadConversations,
    setPreset,
    setCustomRange,
    setProviders,
    setDatabases,
    setModel,
  }
})
