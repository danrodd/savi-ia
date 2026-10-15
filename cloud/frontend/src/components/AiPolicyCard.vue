<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { consoleApi } from '@/lib/api'
import type { AiPolicy, ClientUser } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; policy: AiPolicy }>()
const emit = defineEmits<{ saved: [] }>()

const PROVIDERS = [
  { key: 'claude', label: 'Claude' },
  { key: 'gemini', label: 'Gemini' },
  { key: 'openai', label: 'OpenAI' },
] as const
type ProviderKey = (typeof PROVIDERS)[number]['key']

const AMOUNT = /^\d{1,8}(\.\d{1,4})?$/

const allowed = ref<Record<ProviderKey, boolean>>({ claude: true, gemini: true, openai: true })
const userMonthly = ref('')
const caps = ref<Record<ProviderKey, string>>({ claude: '', gemini: '', openai: '' })
const overrides = ref<{ user_ref: string; amount: string }[]>([])
const people = ref<ClientUser[]>([])

const newRef = ref('')
const newAmount = ref('')
const confirming = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)

function hydrate(policy: AiPolicy): void {
  const list = policy.allowed_providers
  allowed.value = {
    claude: list === null || list.includes('claude'),
    gemini: list === null || list.includes('gemini'),
    openai: list === null || list.includes('openai'),
  }
  userMonthly.value = policy.user_monthly_usd ?? ''
  caps.value = {
    claude: policy.provider_monthly_usd.claude ?? '',
    gemini: policy.provider_monthly_usd.gemini ?? '',
    openai: policy.provider_monthly_usd.openai ?? '',
  }
  overrides.value = Object.entries(policy.user_overrides).map(([user_ref, amount]) => ({
    user_ref,
    amount,
  }))
}

watch(() => props.policy, hydrate, { immediate: true })

onMounted(async () => {
  try {
    people.value = await consoleApi.clientUsers(props.clientId)
  } catch {
    people.value = []
  }
})

function personLabel(ref: string): string {
  const found = people.value.find((p) => p.user_ref === ref)
  return found?.label ?? `${ref.slice(0, 8)}…`
}

const candidates = computed(() =>
  people.value.filter((p) => !overrides.value.some((o) => o.user_ref === p.user_ref)),
)

const hasCap = computed(
  () =>
    userMonthly.value.trim() !== '' ||
    overrides.value.length > 0 ||
    PROVIDERS.some((p) => caps.value[p.key].trim() !== ''),
)

/** Gemini y OpenAI no informan su costo: sin precio cargado en SAVI, el tope no se puede medir. */
const priceWarning = computed(() => hasCap.value && (allowed.value.gemini || allowed.value.openai))

const noneAllowed = computed(() => PROVIDERS.every((p) => !allowed.value[p.key]))

function validAmount(value: string): boolean {
  return AMOUNT.test(value.trim())
}

function addOverride(): void {
  error.value = null
  if (!newRef.value || !validAmount(newAmount.value)) {
    error.value = 'Elegí una persona y un monto en USD (por ejemplo 20 o 7.50).'
    return
  }
  overrides.value.push({ user_ref: newRef.value, amount: newAmount.value.trim() })
  newRef.value = ''
  newAmount.value = ''
}

function removeOverride(ref: string): void {
  overrides.value = overrides.value.filter((o) => o.user_ref !== ref)
}

function buildBody(): AiPolicy | null {
  const amounts = [userMonthly.value, ...PROVIDERS.map((p) => caps.value[p.key])].filter(
    (v) => v.trim() !== '',
  )
  if (amounts.some((v) => !validAmount(v))) {
    error.value = 'Los montos van en USD, con hasta 4 decimales (por ejemplo 5 o 12.50).'
    return null
  }
  if (noneAllowed.value) {
    error.value = 'Dejá al menos un proveedor habilitado.'
    return null
  }
  const every = PROVIDERS.every((p) => allowed.value[p.key])
  const providerCaps: Record<string, string> = {}
  for (const p of PROVIDERS) {
    const value = caps.value[p.key].trim()
    if (value) providerCaps[p.key] = value
  }
  return {
    allowed_providers: every
      ? null
      : PROVIDERS.filter((p) => allowed.value[p.key]).map((p) => p.key),
    user_monthly_usd: userMonthly.value.trim() || null,
    provider_monthly_usd: providerCaps,
    user_overrides: Object.fromEntries(overrides.value.map((o) => [o.user_ref, o.amount])),
  }
}

function askToSave(): void {
  error.value = null
  if (buildBody()) confirming.value = true
}

async function save(): Promise<void> {
  const body = buildBody()
  if (!body) {
    confirming.value = false
    return
  }
  busy.value = true
  try {
    await consoleApi.setClientAiPolicy(props.clientId, body)
    emit('saved')
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
    confirming.value = false
  }
}
</script>

<template>
  <section class="card ai" data-test="ai-policy">
    <h2>IA: proveedores y topes</h2>
    <p class="muted">
      SEO Group decide qué proveedores usa cada instalación y cuánto puede gastar. SAVI mide el
      consumo y bloquea antes de responder; el cambio aplica en el próximo contacto de cada
      instalación. Vacío = sin tope.
    </p>
    <p v-if="error" class="error-text" role="alert" data-test="ai-error">{{ error }}</p>

    <fieldset>
      <legend>Proveedores habilitados</legend>
      <label v-for="p in PROVIDERS" :key="p.key" class="check">
        <input v-model="allowed[p.key]" type="checkbox" :data-test="`ai-provider-${p.key}`" />
        {{ p.label }}
      </label>
    </fieldset>

    <label>
      Tope mensual por persona (USD)
      <input
        v-model="userMonthly"
        inputmode="decimal"
        placeholder="Sin tope"
        data-test="ai-user-cap"
      />
    </label>

    <fieldset>
      <legend>Tope mensual de toda la instalación, por proveedor (USD)</legend>
      <label v-for="p in PROVIDERS" :key="p.key">
        {{ p.label }}
        <input
          v-model="caps[p.key]"
          inputmode="decimal"
          placeholder="Sin tope"
          :data-test="`ai-provider-cap-${p.key}`"
        />
      </label>
    </fieldset>

    <fieldset>
      <legend>Excepciones por persona</legend>
      <p class="muted">
        Reemplaza el tope general de esa persona. Con 0 se la deja sin IA. Las personas salen del
        consumo ya registrado.
      </p>
      <ul v-if="overrides.length" class="overrides">
        <li v-for="o in overrides" :key="o.user_ref" data-test="ai-override">
          <strong>{{ personLabel(o.user_ref) }}</strong>
          <span>USD {{ o.amount }}</span>
          <button class="btn btn-small" type="button" @click="removeOverride(o.user_ref)">
            Quitar
          </button>
        </li>
      </ul>
      <div class="row">
        <select v-model="newRef" data-test="ai-override-person" aria-label="Persona">
          <option value="">Elegí una persona</option>
          <option v-for="p in candidates" :key="p.user_ref" :value="p.user_ref">
            {{ p.label ?? `${p.user_ref.slice(0, 8)}…` }}
          </option>
        </select>
        <input
          v-model="newAmount"
          inputmode="decimal"
          placeholder="USD"
          aria-label="Monto en USD"
          data-test="ai-override-amount"
        />
        <button class="btn btn-small" type="button" data-test="ai-override-add" @click="addOverride">
          Agregar
        </button>
      </div>
    </fieldset>

    <p v-if="priceWarning" class="warn-text" data-test="ai-price-warning">
      Gemini y OpenAI no informan su costo: para que el tope funcione, el administrador de la
      instalación tiene que cargar los precios en Proveedores de IA. Sin precio, esos turnos se
      bloquean con un aviso.
    </p>

    <div class="row actions">
      <button class="btn btn-primary" type="button" data-test="ai-save" @click="askToSave">
        Guardar
      </button>
    </div>

    <ConfirmDialog
      :open="confirming"
      title="Guardar proveedores y topes de IA"
      message="Las instalaciones de este cliente aplicarán estos límites en su próximo contacto. Quien llegue al tope no podrá usar el asistente hasta el primer día del mes."
      confirm-label="Guardar límites"
      :busy="busy"
      @confirm="save"
      @cancel="confirming = false"
    />
  </section>
</template>

<style scoped>
.ai {
  display: grid;
  gap: 0.9rem;
}
.ai fieldset {
  display: grid;
  gap: 0.5rem;
  border: 1px solid var(--border, #d0d5dd);
  border-radius: 8px;
  padding: 0.7rem 0.9rem;
  min-width: 0;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
}
.overrides {
  display: grid;
  gap: 0.4rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.overrides li {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  align-items: center;
  justify-content: space-between;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.warn-text {
  margin: 0;
  color: var(--warning, #b54708);
}
</style>
