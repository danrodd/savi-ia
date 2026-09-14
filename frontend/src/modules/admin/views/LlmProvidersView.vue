<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ActivateProviderDialog from '../components/ActivateProviderDialog.vue'
import LlmProviderCard from '../components/LlmProviderCard.vue'
import LlmProviderFormDialog from '../components/LlmProviderFormDialog.vue'
import { useLlmProviderStore } from '../stores/llmProviderStore'
import type {
  LlmProvider,
  LlmProviderKind,
  ProviderTestResponse,
  SaveLlmProviderRequest,
} from '../types'

const store = useLlmProviderStore()
const editing = ref<LlmProvider | null>(null)
const formOpen = ref(false)
const activationTarget = ref<LlmProvider | null>(null)
const formError = ref<string | null>(null)
const testResult = ref<ProviderTestResponse | null>(null)
const activationOpen = computed({
  get: () => activationTarget.value !== null,
  set: (open: boolean) => {
    if (!open) activationTarget.value = null
  },
})

const activeProvider = computed(
  () => store.providers.find((provider) => provider.is_active) ?? null,
)

function canActivate(provider: LlmProvider): boolean {
  return Boolean(
    provider.implemented &&
      provider.configured &&
      provider.chat_model &&
      provider.title_model &&
      (provider.has_credential || provider.credential_kind === 'local_session'),
  )
}

onMounted(() => store.load())

function configure(provider: LlmProvider): void {
  editing.value = provider
  formError.value = null
  testResult.value = null
  formOpen.value = true
}
function requestActivation(provider: LlmProvider): void {
  if (activeProvider.value && activeProvider.value.provider !== provider.provider)
    activationTarget.value = provider
  else void activate(provider)
}
async function activate(provider: LlmProvider): Promise<void> {
  try {
    await store.activate(provider.provider)
    activationTarget.value = null
  } catch (e) {
    formError.value = (e as Error).message
  }
}
async function save(provider: LlmProvider, body: SaveLlmProviderRequest): Promise<void> {
  try {
    await store.save(provider.provider, body)
    formOpen.value = false
  } catch (e) {
    formError.value = (e as Error).message
  }
}
async function test(provider: LlmProvider, body: SaveLlmProviderRequest): Promise<void> {
  try {
    const result: ProviderTestResponse = await store.test(provider.provider, body)
    testResult.value = result
    formError.value = result.ok ? null : result.detail
  } catch (e) {
    formError.value = (e as Error).message
  }
}
</script>

<template>
  <section class="providers-view">
    <header class="providers-view__header"><div><p class="eyebrow">Administración / Integraciones</p><h1>Proveedores de IA</h1><p>Configura la conexión que usará SAVI para responder y consultar el ERP.</p></div><button class="refresh" :disabled="store.loading" @click="store.load">Actualizar</button></header>
    <div v-if="store.error || formError" class="providers-view__error" role="alert">{{ store.error ?? formError }}</div>
    <div v-if="store.loading && store.providers.length === 0" class="providers-view__loading">Cargando proveedores…</div>
    <div v-else class="providers-view__grid"><LlmProviderCard v-for="provider in store.providers" :key="provider.provider" :provider="provider" :can-activate="canActivate(provider)" activate-reason="Configura credencial y modelos antes de activar" @configure="configure(provider)" @activate="requestActivation(provider)" /></div>
    <LlmProviderFormDialog v-if="editing" v-model:open="formOpen" :provider="editing" :saving="store.saving" :testing="store.testing" :test-result="testResult" @save="save(editing, $event)" @test="test(editing, $event)" />
    <ActivateProviderDialog v-model:open="activationOpen" :provider="activationTarget" :activating="store.activating" @confirm="activationTarget && activate(activationTarget)" />
  </section>
</template>

<style scoped>
.providers-view { padding: var(--space-5) 0 var(--space-9); }.providers-view__header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-6); margin-bottom: var(--space-7); }.eyebrow { margin: 0 0 var(--space-2); color: var(--brand); font-size: 11px; font-weight: var(--fw-semibold); text-transform: uppercase; letter-spacing: .08em; } h1 { margin: 0; font-family: var(--font-display); font-size: 30px; letter-spacing: -.02em; }.providers-view__header p:last-child { margin: var(--space-3) 0 0; color: var(--text-muted); }.refresh { padding: var(--space-3) var(--space-4); color: var(--text); background: var(--surface-elev); border: 1px solid var(--border); border-radius: var(--r-md); cursor: pointer; }.providers-view__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--space-5); }.providers-view__error { margin-bottom: var(--space-5); padding: var(--space-4); color: var(--danger); background: var(--brand-soft); border: 1px solid var(--brand); border-radius: var(--r-md); }.providers-view__loading { color: var(--text-muted); } @media (max-width: 600px) { .providers-view__header { flex-direction: column; } h1 { font-size: 26px; } }
</style>
