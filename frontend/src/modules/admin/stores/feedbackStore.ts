import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { feedbackAdminService } from '../services/feedbackService'
import type { FeedbackFilters, FeedbackItem, FeedbackSummary } from '../types'
import { buildFeedbackQuery, emptyFeedbackFilters, FEEDBACK_PAGE_SIZE } from '../utils/feedback'

const EXPORT_PAGE = 200
const EXPORT_MAX_ROWS = 10_000

export const useFeedbackStore = defineStore('admin-feedback', () => {
  const filters = ref<FeedbackFilters>(emptyFeedbackFilters())
  const items = ref<FeedbackItem[]>([])
  const total = ref(0)
  const page = ref(0)
  const summary = ref<FeedbackSummary | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / FEEDBACK_PAGE_SIZE)))

  /** Última carga pedida: una respuesta vieja no pisa a una más reciente. */
  let requestSeq = 0

  async function load(): Promise<void> {
    const seq = ++requestSeq
    loading.value = true
    error.value = null
    try {
      const [list, sum] = await Promise.all([
        feedbackAdminService.list(
          buildFeedbackQuery(filters.value, {
            limit: FEEDBACK_PAGE_SIZE,
            offset: page.value * FEEDBACK_PAGE_SIZE,
          }),
        ),
        feedbackAdminService.summary(buildFeedbackQuery(filters.value)),
      ])
      if (seq !== requestSeq) return
      items.value = list.items
      total.value = list.total
      summary.value = sum
    } catch (e) {
      if (seq !== requestSeq) return
      error.value = (e as Error).message || 'No se pudo cargar el feedback.'
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  /** Cambiar un filtro vuelve a la primera página. */
  async function applyFilters(next: FeedbackFilters): Promise<void> {
    filters.value = { ...next }
    page.value = 0
    await load()
  }

  async function goToPage(index: number): Promise<void> {
    page.value = Math.min(Math.max(0, index), pageCount.value - 1)
    await load()
  }

  function exportCsv(): Promise<Blob> {
    return feedbackAdminService.exportCsv(buildFeedbackQuery(filters.value))
  }

  /** Todas las filas del filtro actual (páginas de 200, tope del export). */
  async function fetchAllItems(): Promise<FeedbackItem[]> {
    const all: FeedbackItem[] = []
    for (let offset = 0; offset < EXPORT_MAX_ROWS; offset += EXPORT_PAGE) {
      const chunk = await feedbackAdminService.list(
        buildFeedbackQuery(filters.value, { limit: EXPORT_PAGE, offset }),
      )
      all.push(...chunk.items)
      if (all.length >= chunk.total || chunk.items.length === 0) break
    }
    return all
  }

  return {
    filters,
    items,
    total,
    page,
    pageCount,
    summary,
    loading,
    error,
    load,
    applyFilters,
    goToPage,
    exportCsv,
    fetchAllItems,
  }
})
