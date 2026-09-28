/**
 * Pinia store de los sitios web del conocimiento (administración).
 *
 * Mientras algún sitio esté en cola o leyéndose, la lista se refresca sola.
 * Como en los documentos, el polling lo arranca y lo detiene la vista.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { webSourceService } from '../services/webSourceService'
import type {
  CreateWebSourceRequest,
  PreviewWebSourceRequest,
  UpdateWebSourceRequest,
  WebSource,
  WebSourceDetail,
  WebSourcePreview,
} from '../types'
import { normalizePermissions } from '../utils/companyDocuments'
import { isWebInProgress } from '../utils/webSources'

// Un sitio tarda minutos en leerse: 5 s alcanza y no satura el backend.
export const WEB_POLL_INTERVAL_MS = 5000

export const useWebSourceStore = defineStore('webSources', () => {
  const sources = ref<WebSource[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let polling = false

  const hasInProgress = computed(() => sources.value.some((s) => isWebInProgress(s.status)))

  function upsert(source: WebSource): void {
    const index = sources.value.findIndex((s) => s.id === source.id)
    if (index === -1) sources.value.unshift(source)
    else sources.value.splice(index, 1, source)
  }

  async function refresh(): Promise<void> {
    sources.value = await webSourceService.list()
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await refresh()
      loaded.value = true
    } catch (e) {
      error.value = (e as Error).message || 'No se pudieron cargar los sitios web.'
    } finally {
      loading.value = false
    }
    scheduleNextPoll()
  }

  function scheduleNextPoll(): void {
    if (pollTimer !== null) clearTimeout(pollTimer)
    pollTimer = null
    if (!polling || !hasInProgress.value) return
    pollTimer = setTimeout(async () => {
      pollTimer = null
      try {
        await refresh()
      } catch {
        // Un fallo transitorio no corta el polling; la próxima vuelta reintenta.
      }
      scheduleNextPoll()
    }, WEB_POLL_INTERVAL_MS)
  }

  function startPolling(): void {
    polling = true
    scheduleNextPoll()
  }

  function stopPolling(): void {
    polling = false
    if (pollTimer !== null) clearTimeout(pollTimer)
    pollTimer = null
  }

  /** Detalle con las páginas; de paso actualiza la fila del listado. */
  async function getDetail(id: string): Promise<WebSourceDetail> {
    const detail = await webSourceService.get(id)
    const { pages: _pages, ...source } = detail
    upsert(source)
    scheduleNextPoll()
    return detail
  }

  /** No guarda nada: descubre las páginas y lee la primera. */
  function preview(body: PreviewWebSourceRequest): Promise<WebSourcePreview> {
    return webSourceService.preview(body)
  }

  async function create(body: CreateWebSourceRequest): Promise<WebSource> {
    const created = await webSourceService.create({ ...body, ...normalizePermissions(body) })
    upsert(created)
    scheduleNextPoll()
    return created
  }

  async function update(id: string, body: UpdateWebSourceRequest): Promise<WebSource> {
    const updated = await webSourceService.update(id, body)
    upsert(updated)
    return updated
  }

  async function refreshNow(id: string): Promise<WebSource> {
    const queued = await webSourceService.refresh(id)
    upsert(queued)
    scheduleNextPoll()
    return queued
  }

  async function remove(id: string): Promise<void> {
    await webSourceService.remove(id)
    sources.value = sources.value.filter((s) => s.id !== id)
  }

  return {
    sources,
    loading,
    loaded,
    error,
    hasInProgress,
    load,
    startPolling,
    stopPolling,
    getDetail,
    preview,
    create,
    update,
    refreshNow,
    remove,
  }
})
