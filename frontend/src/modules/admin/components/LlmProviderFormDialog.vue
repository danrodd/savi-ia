<script setup lang="ts">
import { FlaskConical } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { recommendModel } from '../lib/modelRecommendation'
import type {
  LlmCredentialKind,
  LlmProvider,
  ModelPricing,
  ProviderModel,
  SaveLlmProviderRequest,
} from '../types'
import ModelPricingTable from './ModelPricingTable.vue'
import ProviderIcon from './ProviderIcon.vue'

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
const modelSearch = ref('')
const testDetail = ref<string | null>(null)

const isLocalSession = computed(
  () => props.provider?.provider === 'claude' && credentialKind.value === 'local_session',
)
const selectedModels = computed(() =>
  [chatModel.value, titleModel.value].filter(
    (value, index, all) => value && all.indexOf(value) === index,
  ),
)
const modelFallbackHint = computed(() => {
  if (props.provider?.provider === 'claude' && credentialKind.value === 'local_session') {
    return 'El login local de Claude no expone un catálogo de modelos. Escribe sus identificadores manualmente.'
  }
  if (props.provider?.provider === 'claude' && props.provider.supports_model_listing) {
    return 'No se pudieron obtener los modelos de Anthropic. Puedes escribir sus identificadores manualmente.'
  }
  return 'Este proveedor no lista modelos. Escribe sus identificadores manualmente.'
})
// El proveedor puede haber dado de baja el modelo que ya estaba guardado
// (nos pasó con Gemini 2.5): si el catálogo nuevo no lo trae, lo agregamos
// igual para no dejar el select en blanco y perder de vista qué había.
const catalogModels = computed(() => {
  const known = new Set(models.value.map((model) => model.id))
  const missing = [chatModel.value, titleModel.value].filter(
    (id, index, all) => id && !known.has(id) && all.indexOf(id) === index,
  )
  if (missing.length === 0) return models.value
  return [
    ...models.value,
    ...missing.map((id) => ({ id, display_name: `${id} (ya no está en el catálogo)` })),
  ]
})
const filteredModels = computed(() => {
  const query = modelSearch.value.trim().toLowerCase()
  if (!query) return catalogModels.value
  return catalogModels.value.filter((model) =>
    `${model.display_name} ${model.id}`.toLowerCase().includes(query),
  )
})

const recommendedModel = computed(() => recommendModel(models.value))

function reset(provider: LlmProvider | null): void {
  credentialKind.value = provider?.credential_kind ?? provider?.credential_kinds[0] ?? 'api_key'
  credential.value = ''
  chatModel.value = provider?.chat_model ?? ''
  titleModel.value = provider?.title_model ?? ''
  pricing.value = Object.fromEntries(
    Object.entries(provider?.pricing ?? {}).map(([key, value]) => [key, { ...value }]),
  )
  models.value = []
  modelSearch.value = ''
  testDetail.value = null
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    reset(props.provider)
    // Ya hay una credencial guardada: traemos el catálogo sin pedirle al
    // usuario que la vuelva a pegar solo para cambiar el modelo.
    if (
      props.provider?.has_credential &&
      props.provider.implemented &&
      props.provider.supports_model_listing &&
      credentialKind.value !== 'local_session'
    ) {
      handleTest()
    }
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
    const recommended = recommendedModel.value?.id ?? ''
    if (!chatModel.value) chatModel.value = recommended
    if (!titleModel.value) titleModel.value = recommended
  }
}

defineExpose({ applyTestResult })
</script>

<template>
  <Dialog :open="open" :title="`${provider?.configured ? 'Editar' : 'Configurar'} ${provider?.display_name ?? 'proveedor'}`" :max-width="760" @update:open="emit('update:open', $event)">
    <template #leading>
      <ProviderIcon v-if="provider" :kind="provider.provider" :size="24" />
    </template>
    <form class="form" @submit.prevent="handleSave">
      <label>Tipo de credencial<select v-model="credentialKind"><option v-for="kind in provider?.credential_kinds" :key="kind" :value="kind">{{ kind }}</option></select></label>
      <div v-if="isLocalSession" class="form__note">Claude usará el login local de este equipo. No necesitas introducir una credencial aquí.</div>
      <label v-else>Credencial<input v-model="credential" type="password" autocomplete="new-password" :placeholder="provider?.has_credential ? 'Ya hay una guardada — dejala vacía para conservarla' : 'Pegá la API key'" /></label>
      <p v-if="provider?.has_credential && !credential" class="form__note">🔒 Ya hay una credencial guardada. Podés cambiar solo el modelo sin volver a pegarla.</p>
       <div class="form__test"><Button type="button" variant="secondary" :loading="testing" :disabled="!provider?.implemented" @click="handleTest"><FlaskConical :size="15" aria-hidden="true" /> Probar credencial</Button><span v-if="testDetail" data-testid="provider-test-detail" :class="{ 'form__ok': testResult?.ok }">{{ testDetail }}</span></div>
      <div v-if="models.length > 0" class="form__models">
        <div class="form__catalog-head">
          <div><strong>Catálogo de modelos</strong><span>{{ models.length }} disponibles</span></div>
          <input v-model="modelSearch" class="form__search" type="search" placeholder="Buscar modelo…" aria-label="Buscar modelo" />
        </div>
        <p v-if="recommendedModel" class="form__recommendation">Recomendado: <strong>{{ recommendedModel.display_name }}</strong> ({{ recommendedModel.id }}). Puedes cambiarlo manualmente.</p>
        <label>Modelo de chat<select v-model="chatModel"><option v-for="model in filteredModels" :key="model.id" :value="model.id">{{ model.display_name }}{{ model.id === recommendedModel?.id ? ' · recomendado' : '' }} ({{ model.id }})</option></select></label>
        <label>Modelo de títulos<select v-model="titleModel"><option v-for="model in filteredModels" :key="model.id" :value="model.id">{{ model.display_name }}{{ model.id === recommendedModel?.id ? ' · recomendado' : '' }} ({{ model.id }})</option></select></label>
        <p v-if="filteredModels.length === 0" class="form__hint">No hay modelos que coincidan con la búsqueda.</p>
      </div>
      <div v-else class="form__models"><label>Modelo de chat<input v-model="chatModel" placeholder="ID del modelo" required /></label><label>Modelo de títulos<input v-model="titleModel" placeholder="ID del modelo" required /></label><p class="form__hint">{{ modelFallbackHint }}</p></div>
      <ModelPricingTable :models="selectedModels" :pricing="pricing" />
      <footer class="form__footer"><Button type="button" variant="ghost" @click="emit('update:open', false)">Cancelar</Button><Button type="submit" :loading="saving">Guardar</Button></footer>
    </form>
  </Dialog>
</template>

<style scoped>
.form { display: grid; gap: var(--space-5); } label { display: grid; gap: var(--space-2); color: var(--text-muted); font-size: 12px; font-weight: var(--fw-medium); } input, select { width: 100%; min-height: 38px; padding: 0 var(--space-3); color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-sm); font: inherit; } input:focus-visible, select:focus-visible { outline: 2px solid var(--brand-ring); outline-offset: 1px; border-color: var(--brand); } .form__note, .form__hint { margin: 0; padding: var(--space-3); color: var(--text-muted); background: var(--surface-subtle); border-radius: var(--r-sm); font-size: 12px; }.form__hint { grid-column: 1 / -1; } .form__test { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }.form__test span { color: var(--danger); font-size: 12px; }.form__test .form__ok { color: var(--success); }.form__models { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); padding: var(--space-4); background: var(--surface-subtle); border: 1px solid var(--border); border-radius: var(--r-md); }.form__catalog-head { grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }.form__catalog-head div { display: flex; flex-direction: column; gap: 2px; color: var(--text); }.form__catalog-head span { color: var(--text-subtle); font-size: 11px; font-weight: var(--fw-regular); }.form__search { max-width: 220px; min-height: 34px; }.form__recommendation { grid-column: 1 / -1; margin: calc(-1 * var(--space-2)) 0 0; color: var(--text-muted); font-size: 12px; }.form__footer { display: flex; justify-content: flex-end; gap: var(--space-3); } @media (max-width: 600px) { .form__models { grid-template-columns: 1fr; } .form__catalog-head { align-items: stretch; flex-direction: column; } .form__search { max-width: none; } }
</style>
