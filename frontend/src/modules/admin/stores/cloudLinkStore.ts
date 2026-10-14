import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { cloudLinkService } from '../services/cloudLinkService'
import type { CloudHistoryMode, CloudLinkState, CloudPreview } from '../types'
import { cloudLinkErrorMessage, needsGlobalAlert } from '../utils/cloudLink'

export const useCloudLinkStore = defineStore('admin-cloud-link', () => {
  const state = ref<CloudLinkState | null>(null)
  const preview = ref<CloudPreview | null>(null)
  const loading = ref(false)
  const previewLoading = ref(false)
  const error = ref<string | null>(null)
  const previewError = ref<string | null>(null)

  const isLinked = computed(() => !!state.value && state.value.status !== 'unlinked')
  const showGlobalAlert = computed(() => needsGlobalAlert(state.value))

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      state.value = await cloudLinkService.status()
    } catch (e) {
      error.value = cloudLinkErrorMessage(e, 'No se pudo consultar el estado de SAVI Cloud.')
    } finally {
      loading.value = false
    }
  }

  /** Lanza con un mensaje ya amigable si Cloud rechaza el token. */
  async function link(token: string, history: CloudHistoryMode): Promise<void> {
    try {
      state.value = await cloudLinkService.link(token.trim(), history)
      preview.value = null
    } catch (e) {
      throw new Error(cloudLinkErrorMessage(e, 'No se pudo vincular con SAVI Cloud.'))
    }
  }

  async function unlink(): Promise<void> {
    try {
      await cloudLinkService.unlink()
    } catch (e) {
      throw new Error(cloudLinkErrorMessage(e, 'No se pudo desvincular.'))
    }
    preview.value = null
    await load()
  }

  async function syncNow(): Promise<void> {
    try {
      await cloudLinkService.syncNow()
    } catch (e) {
      throw new Error(cloudLinkErrorMessage(e, 'No se pudo iniciar la sincronización.'))
    }
    await load()
  }

  async function loadPreview(): Promise<void> {
    previewLoading.value = true
    previewError.value = null
    try {
      preview.value = await cloudLinkService.preview()
    } catch (e) {
      previewError.value = cloudLinkErrorMessage(e, 'No se pudo armar la vista previa.')
    } finally {
      previewLoading.value = false
    }
  }

  return {
    state,
    preview,
    loading,
    previewLoading,
    error,
    previewError,
    isLinked,
    showGlobalAlert,
    load,
    link,
    unlink,
    syncNow,
    loadPreview,
  }
})
