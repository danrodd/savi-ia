/**
 * Pinia store de los documentos de la empresa (administración).
 *
 * Mientras haya documentos en cola o procesándose, la lista se refresca sola
 * cada 3 s. El polling lo arranca y lo detiene la vista (`startPolling` /
 * `stopPolling`): el store no sabe si hay alguien mirando.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { companyDocumentService } from '../services/companyDocumentService'
import type {
  AiReadingSettings,
  CompanyDocument,
  CompanyDocumentUsage,
  DocumentPermissions,
  UpdateCompanyDocumentRequest,
} from '../types'
import { isInProgress, normalizePermissions } from '../utils/companyDocuments'

export const POLL_INTERVAL_MS = 3000

export const useCompanyDocumentStore = defineStore('companyDocuments', () => {
  const documents = ref<CompanyDocument[]>([])
  const usage = ref<CompanyDocumentUsage | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** `null` hasta cargarla; si falla, la subida sigue funcionando sin estimado. */
  const aiReading = ref<AiReadingSettings | null>(null)
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let polling = false

  const hasInProgress = computed(() => documents.value.some((d) => isInProgress(d.status)))

  function upsert(document: CompanyDocument): void {
    const index = documents.value.findIndex((d) => d.id === document.id)
    if (index === -1) documents.value.unshift(document)
    else documents.value.splice(index, 1, document)
  }

  async function refresh(): Promise<void> {
    const [list, stats] = await Promise.all([
      companyDocumentService.list(),
      companyDocumentService.usage(),
    ])
    documents.value = list
    usage.value = stats
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await refresh()
    } catch (e) {
      error.value = (e as Error).message || 'No se pudieron cargar los documentos.'
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
    }, POLL_INTERVAL_MS)
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

  async function upload(
    file: File,
    title: string,
    permissions: DocumentPermissions,
  ): Promise<CompanyDocument> {
    const created = await companyDocumentService.upload(
      file,
      title,
      normalizePermissions(permissions),
    )
    upsert(created)
    scheduleNextPoll()
    return created
  }

  async function update(id: string, body: UpdateCompanyDocumentRequest): Promise<CompanyDocument> {
    const updated = await companyDocumentService.update(id, body)
    upsert(updated)
    return updated
  }

  async function replace(id: string, file: File): Promise<CompanyDocument> {
    const replaced = await companyDocumentService.replace(id, file)
    upsert(replaced)
    scheduleNextPoll()
    return replaced
  }

  async function reprocess(id: string): Promise<CompanyDocument> {
    const queued = await companyDocumentService.reprocess(id)
    upsert(queued)
    scheduleNextPoll()
    return queued
  }

  async function loadAiReading(): Promise<void> {
    try {
      aiReading.value = await companyDocumentService.aiReadingSettings()
    } catch {
      aiReading.value = null
    }
  }

  async function setAiReading(
    enabled: boolean,
    acceptProvider?: string,
  ): Promise<AiReadingSettings> {
    const saved = await companyDocumentService.updateAiReadingSettings(enabled, acceptProvider)
    aiReading.value = saved
    return saved
  }

  async function readWithAi(id: string): Promise<CompanyDocument> {
    const queued = await companyDocumentService.readWithAi(id)
    upsert(queued)
    scheduleNextPoll()
    return queued
  }

  async function remove(id: string): Promise<void> {
    await companyDocumentService.remove(id)
    documents.value = documents.value.filter((d) => d.id !== id)
  }

  return {
    documents,
    usage,
    loading,
    error,
    aiReading,
    hasInProgress,
    load,
    refresh,
    startPolling,
    stopPolling,
    upload,
    update,
    replace,
    reprocess,
    readWithAi,
    loadAiReading,
    setAiReading,
    remove,
  }
})
