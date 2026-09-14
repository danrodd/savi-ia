<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import type {
  LlmCredentialKind,
  LlmProvider,
  ModelPricing,
  ProviderModel,
  SaveLlmProviderRequest,
} from '../types'
import ModelPricingTable from './ModelPricingTable.vue'

const props = defineProps<{
  open: boolean
  provider: LlmProvider | null
  saving?: boolean
  testing?: boolean
  testResult?: { ok: boolean; detail: string; models: ProviderModel[] } | null
}>()
const emit = defineEmits<{
  'update:open': [boolean]
  save: [SaveLlmProviderRequest]
  test: [SaveLlmProviderRequest]
}>()

const credentialKind = ref<LlmCredentialKind>('api_key')
const credential = ref('')
const chatModel = ref('')
const titleModel = ref('')
const pricing = ref<Record<string, ModelPricing>>({})
const models = ref<ProviderModel[]>([])
const testDetail = ref<string | null>(null)

const isLocalSession = computed(
  () => props.provider?.provider === 'claude' && credentialKind.value === 'local_session',
)
const selectedModels = computed(() =>
  [chatModel.value, titleModel.value].filter(
    (value, index, all) => value && all.indexOf(value) === index,
  ),
)

function reset(provider: LlmProvider | null): void {
  credentialKind.value = provider?.credential_kind ?? provider?.credential_kinds[0] ?? 'api_key'
  credential.value = ''
  chatModel.value = provider?.chat_model ?? ''
  titleModel.value = provider?.title_model ?? ''
  pricing.value = Object.fromEntries(
    Object.entries(provider?.pricing ?? {}).map(([key, value]) => [key, { ...value }]),
  )
  models.value = []
  testDetail.value = null
}

watch(
  () => props.open,
  (open) => {
    if (open) reset(props.provider)
  },
)
watch(
  () => props.testResult,
  (result) => {
    if (result) applyTestResult(result)
  },
)
watch(credentialKind, (kind) => {
  if (kind === 'local_session') credential.value = ''
})

function request(): SaveLlmProviderRequest {
  const body: SaveLlmProviderRequest = {
    credential_kind: credentialKind.value,
    chat_model: chatModel.value.trim(),
    title_model: titleModel.value.trim(),
    pricing: pricing.value,
  }
  if (credential.value) body.credential = credential.value
  return body
}

function handleTest(): void {
  testDetail.value = null
  emit('test', request())
}
function handleSave(): void {
  emit('save', request())
}
function applyTestResult(result: { ok: boolean; detail: string; models: ProviderModel[] }): void {
  testDetail.value = result.detail
  if (result.ok && result.models.length > 0) {
    models.value = result.models
    if (!chatModel.value) chatModel.value = result.models[0]?.id ?? ''
    if (!titleModel.value) titleModel.value = result.models[0]?.id ?? ''
  }
}

defineExpose({ applyTestResult })
</script>

<template>
  <Dialog :open="open" :title="`${provider?.configured ? 'Editar' : 'Configurar'} ${provider?.display_name ?? 'proveedor'}`" :max-width="760" @update:open="emit('update:open', $event)">
    <form class="form" @submit.prevent="handleSave">
      <label>Tipo de credencial<select v-model="credentialKind"><option v-for="kind in provider?.credential_kinds" :key="kind" :value="kind">{{ kind }}</option></select></label>
      <div v-if="isLocalSession" class="form__note">Claude usará el login local de este equipo. No necesitas introducir una credencial aquí.</div>
      <label v-else>Credencial<input v-model="credential" type="password" autocomplete="new-password" placeholder="Déjala vacía para conservar la actual" /></label>
       <div class="form__test"><Button type="button" variant="secondary" :loading="testing" :disabled="!provider?.implemented" @click="handleTest">Probar credencial</Button><span v-if="testDetail" :class="{ 'form__ok': testResult?.ok }">{{ testDetail }}</span></div>
      <div v-if="models.length > 0" class="form__models">
        <label>Modelo de chat<select v-model="chatModel"><option v-for="model in models" :key="model.id" :value="model.id">{{ model.display_name }} ({{ model.id }})</option></select></label>
        <label>Modelo de títulos<select v-model="titleModel"><option v-for="model in models" :key="model.id" :value="model.id">{{ model.display_name }} ({{ model.id }})</option></select></label>
      </div>
      <div v-else class="form__models"><label>Modelo de chat<input v-model="chatModel" placeholder="ID del modelo" required /></label><label>Modelo de títulos<input v-model="titleModel" placeholder="ID del modelo" required /></label><p class="form__hint">Este proveedor no lista modelos. Escribe sus identificadores manualmente.</p></div>
      <ModelPricingTable :models="selectedModels" :pricing="pricing" />
      <footer class="form__footer"><Button type="button" variant="ghost" @click="emit('update:open', false)">Cancelar</Button><Button type="submit" :loading="saving">Guardar</Button></footer>
    </form>
  </Dialog>
</template>

<style scoped>
.form { display: grid; gap: var(--space-5); } label { display: grid; gap: var(--space-2); color: var(--text-muted); font-size: 12px; font-weight: var(--fw-medium); } input, select { width: 100%; min-height: 36px; padding: 0 var(--space-3); color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-sm); font: inherit; } .form__note, .form__hint { margin: 0; padding: var(--space-3); color: var(--text-muted); background: var(--surface-subtle); border-radius: var(--r-sm); font-size: 12px; }.form__hint { grid-column: 1 / -1; } .form__test { display: flex; align-items: center; gap: var(--space-4); }.form__test span { color: var(--danger); font-size: 12px; }.form__test .form__ok { color: var(--success); }.form__models { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }.form__footer { display: flex; justify-content: flex-end; gap: var(--space-3); } @media (max-width: 600px) { .form__models { grid-template-columns: 1fr; } }
</style>
