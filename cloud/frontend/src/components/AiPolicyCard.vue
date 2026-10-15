<script setup lang="ts">
import {
  Alert,
  Button,
  Card,
  Checkbox,
  EmptyState,
  Select,
  TextField,
  toast,
  UnsavedBar,
  useZodForm,
} from '@savi/ui'
import { UserRound, X } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import LinkingEmptyState from '@/components/LinkingEmptyState.vue'
import { useClientPeople } from '@/composables/useClientPeople'
import { useLeaveGuard } from '@/composables/useLeaveGuard'
import { consoleApi } from '@/lib/api'
import { formatUsd } from '@/lib/format'
import {
  AMOUNT,
  AMOUNT_HINT,
  aiPolicySchema,
  PROVIDERS,
  toBody,
  toForm,
} from '@/lib/schemas/aiPolicy'
import type { AiPolicy } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string; policy: AiPolicy }>()
const emit = defineEmits<{ saved: [] }>()

const form = useZodForm(aiPolicySchema, toForm(props.policy))
watch(
  () => props.policy,
  (policy) => form.reset(toForm(policy)),
)

useLeaveGuard(form.isDirty)

// Las excepciones ya guardadas se muestran aunque la persona no esté en el padrón.
const { people, loaded, personLabel } = useClientPeople(() => props.clientId)

// Alta de una excepción: se valida acá, aparte del formulario principal.
const newRef = ref<string | null>(null)
const newAmount = ref('')
const newError = ref<{ person?: string; amount?: string }>({})

const candidates = computed(() =>
  people.value
    .filter((p) => !form.values.overrides.some((o) => o.user_ref === p.user_ref))
    .map((p) => ({ value: p.user_ref, label: personLabel(p.user_ref) })),
)

function addOverride(): void {
  newError.value = {}
  if (!newRef.value) newError.value.person = 'Elegí una persona.'
  if (!AMOUNT.test(newAmount.value.trim())) newError.value.amount = AMOUNT_HINT
  if (!newRef.value || newError.value.amount) return
  form.values.overrides.push({ user_ref: newRef.value, amount: newAmount.value.trim() })
  newRef.value = null
  newAmount.value = ''
}

function removeOverride(ref: string): void {
  form.values.overrides = form.values.overrides.filter((o) => o.user_ref !== ref)
}

const hasCap = computed(
  () =>
    form.values.userMonthly.trim() !== '' ||
    form.values.overrides.length > 0 ||
    PROVIDERS.some((p) => form.values.caps[p.key].trim() !== ''),
)

/** Gemini y OpenAI no informan su costo: sin precio cargado en SAVI, el tope no se puede medir. */
const priceWarning = computed(
  () => hasCap.value && (form.values.allowed.gemini || form.values.allowed.openai),
)

const confirming = ref(false)
const busy = ref(false)

function askToSave(): void {
  void form.handleSubmit(() => {
    confirming.value = true
  })
}

async function save(): Promise<void> {
  const parsed = aiPolicySchema.safeParse(form.values)
  if (!parsed.success) {
    confirming.value = false
    return
  }
  busy.value = true
  try {
    await consoleApi.setClientAiPolicy(props.clientId, toBody(parsed.data))
    toast.success('Límites de IA guardados', {
      description: 'Las instalaciones los aplican en su próximo contacto.',
    })
    emit('saved')
  } catch (e) {
    toast.error('No se pudieron guardar los límites', { description: errorMessage(e) })
  } finally {
    busy.value = false
    confirming.value = false
  }
}
</script>

<template>
  <div class="ai" data-test="ai-policy">
    <Card
      title="Proveedores habilitados"
      description="Qué proveedores de IA pueden usar las instalaciones de este cliente."
    >
      <div class="ai__providers">
        <Checkbox
          v-for="p in PROVIDERS"
          :key="p.key"
          v-model="form.values.allowed[p.key]"
          :label="p.label"
          :data-test="`ai-provider-${p.key}`"
          @update:model-value="form.touch('allowed')"
        />
      </div>
      <Alert v-if="form.errors.value.allowed" tone="danger" class="ai__alert" data-test="ai-error">
        {{ form.errors.value.allowed }}
      </Alert>
    </Card>

    <Card
      title="Topes mensuales"
      description="SAVI mide el consumo y bloquea antes de responder. Vacío = sin tope. Se reinician el primer día de cada mes."
    >
      <div class="form-grid">
        <TextField
          v-model="form.values.userMonthly"
          class="form-grid__wide"
          label="Por persona (USD)"
          inputmode="decimal"
          placeholder="Sin tope"
          hint="Lo máximo que puede gastar cada persona en el mes, con cualquier proveedor."
          :error="form.errors.value.userMonthly"
          data-test="ai-user-cap"
          @blur="form.touch('userMonthly')"
        />
      </div>
      <p class="ai__subtitle">De toda la instalación, por proveedor</p>
      <div class="form-grid form-grid--3">
        <TextField
          v-for="p in PROVIDERS"
          :key="p.key"
          v-model="form.values.caps[p.key]"
          :label="`${p.label} (USD)`"
          inputmode="decimal"
          placeholder="Sin tope"
          :disabled="!form.values.allowed[p.key]"
          :error="form.errors.value[`caps.${p.key}`]"
          :data-test="`ai-provider-cap-${p.key}`"
          @blur="form.touch(`caps.${p.key}`)"
        />
      </div>
      <Alert v-if="priceWarning" tone="warning" class="ai__alert" data-test="ai-price-warning">
        Gemini y OpenAI no informan su costo: para que el tope funcione, el administrador de la
        instalación tiene que cargar los precios en Proveedores de IA. Sin precio, esos turnos se
        bloquean con un aviso.
      </Alert>
    </Card>

    <Card
      title="Excepciones por persona"
      description="Reemplazan el tope por persona. Con 0, la persona queda sin IA. La lista sale de las personas que ya usaron SAVI en este cliente."
    >
      <ul v-if="form.values.overrides.length" class="ai__overrides">
        <li v-for="o in form.values.overrides" :key="o.user_ref" data-test="ai-override">
          <UserRound :size="16" aria-hidden="true" />
          <strong>{{ personLabel(o.user_ref) }}</strong>
          <span class="num">{{ Number(o.amount) === 0 ? 'Sin IA' : `${formatUsd(o.amount)} / mes` }}</span>
          <Button
            variant="ghost"
            size="sm"
            icon
            :aria-label="`Quitar la excepción de ${personLabel(o.user_ref)}`"
            @click="removeOverride(o.user_ref)"
          >
            <X :size="14" aria-hidden="true" />
          </Button>
        </li>
      </ul>
      <EmptyState
        v-else
        title="Sin excepciones"
        description="Todas las personas usan el tope general."
        class="ai__empty"
      />
      <LinkingEmptyState
        v-if="loaded && people.length === 0"
        :client-id="clientId"
        :icon="UserRound"
        title="Todavía no hay personas para elegir"
        description="La lista sale de quienes ya usaron SAVI en este cliente. Aparecen cuando una instalación vinculada reporta su primer uso."
        data-test="ai-no-people"
      />
      <div v-else class="ai__add">
        <Select
          v-model="newRef"
          label="Persona"
          placeholder="Elegí una persona"
          :options="candidates"
          :error="newError.person"
          data-test="ai-override-person"
        />
        <TextField
          v-model="newAmount"
          label="Tope (USD)"
          inputmode="decimal"
          placeholder="20"
          :error="newError.amount"
          data-test="ai-override-amount"
        />
        <Button variant="secondary" class="ai__add-button" data-test="ai-override-add" @click="addOverride">
          Agregar excepción
        </Button>
      </div>
    </Card>

    <UnsavedBar
      :visible="form.isDirty.value"
      :saving="busy"
      save-label="Guardar límites"
      @save="askToSave"
      @discard="form.reset()"
    />

    <ConfirmDialog
      :open="confirming"
      title="Guardar proveedores y topes de IA"
      message="Las instalaciones de este cliente aplicarán estos límites en su próximo contacto. Quien llegue al tope no podrá usar el asistente hasta el primer día del mes."
      confirm-label="Guardar límites"
      :busy="busy"
      @confirm="save"
      @cancel="confirming = false"
    />
  </div>
</template>

<style scoped>
.ai {
  display: grid;
  gap: var(--space-6);
}

.ai__providers {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-7);
}

.ai__alert {
  margin-top: var(--space-5);
}

.ai__subtitle {
  margin: var(--space-6) 0 var(--space-3);
  font-size: 12.5px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.ai__overrides {
  display: grid;
  gap: var(--space-2);
  margin: 0 0 var(--space-5);
  padding: 0;
  list-style: none;
}

.ai__overrides li {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  font-size: 13px;
  color: var(--text-muted);
}

.ai__overrides strong {
  flex: 1;
  color: var(--text);
}

.ai__empty {
  padding: var(--space-5) 0 var(--space-6);
}

.ai__add {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--space-4);
  padding-top: var(--space-5);
  border-top: 1px solid var(--border);
}

.ai__add-button {
  margin-top: 21px;
}

@media (max-width: 720px) {
  .ai__add {
    grid-template-columns: minmax(0, 1fr);
  }

  .ai__add-button {
    margin-top: 0;
  }
}
</style>
