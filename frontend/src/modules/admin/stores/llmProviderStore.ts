import { defineStore } from 'pinia'
import { ref } from 'vue'
import { llmProviderService } from '../services/llmProviderService'
import type {
  LlmProvider,
  LlmProviderKind,
  ProviderTestResponse,
  SaveLlmProviderRequest,
} from '../types'

export const useLlmProviderStore = defineStore('llmProviders', () => {
  const providers = ref<LlmProvider[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const saving = ref(false)
  const testing = ref(false)
  const activating = ref(false)

  function replace(provider: LlmProvider): void {
    const index = providers.value.findIndex((item) => item.provider === provider.provider)
    if (index === -1) providers.value.push(provider)
    else providers.value.splice(index, 1, provider)
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      providers.value = await llmProviderService.list()
    } catch (e) {
      error.value = (e as Error).message || 'No se pudieron cargar los proveedores de IA.'
    } finally {
      loading.value = false
    }
  }

  async function save(
    provider: LlmProviderKind,
    body: SaveLlmProviderRequest,
  ): Promise<LlmProvider> {
    saving.value = true
    try {
      const result = await llmProviderService.save(provider, body)
      replace(result)
      return result
    } finally {
      saving.value = false
    }
  }

  async function test(
    provider: LlmProviderKind,
    body: SaveLlmProviderRequest,
  ): Promise<ProviderTestResponse> {
    testing.value = true
    try {
      return await llmProviderService.test(provider, body)
    } finally {
      testing.value = false
    }
  }

  async function activate(provider: LlmProviderKind): Promise<LlmProvider> {
    activating.value = true
    try {
      const result = await llmProviderService.activate(provider)
      providers.value = providers.value.map((item) => ({
        ...item,
        is_active: item.provider === provider,
      }))
      replace(result)
      return result
    } finally {
      activating.value = false
    }
  }

  return { providers, loading, error, saving, testing, activating, load, save, test, activate }
})
