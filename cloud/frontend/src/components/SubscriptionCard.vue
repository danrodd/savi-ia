<script setup lang="ts">
import {
  Alert,
  Badge,
  Button,
  Card,
  DataTable,
  Select,
  Skeleton,
  type TableColumn,
  Textarea,
  TextField,
  type Tone,
  toast,
  useZodForm,
} from '@savi/ui'
import { computed, onMounted, ref } from 'vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime, formatDay, formatUsd } from '@/lib/format'
import { ledgerEntrySchema, planSchema } from '@/lib/schemas/billing'
import type { LedgerEntry, Subscription } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string }>()

const STATUS: Record<Subscription['status'], { label: string; tone: Tone }> = {
  none: { label: 'Sin vencimiento cargado', tone: 'neutral' },
  active: { label: 'Vigente', tone: 'success' },
  expiring: { label: 'Por vencer', tone: 'warning' },
  expired: { label: 'Vencida', tone: 'danger' },
}

const KINDS = [
  { value: 'payment' as const, label: 'Pago recibido' },
  { value: 'adjustment' as const, label: 'Ajuste (corrección o cortesía)' },
]

const LEDGER_COLUMNS: TableColumn[] = [
  { key: 'created_at', label: 'Fecha', width: '150px' },
  { key: 'kind', label: 'Tipo', width: '90px' },
  { key: 'amount_usd', label: 'Monto', align: 'right', width: '110px' },
  { key: 'note', label: 'Referencia' },
  { key: 'created_by', label: 'Registró' },
]

const subscription = ref<Subscription | null>(null)
const ledger = ref<LedgerEntry[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

const plan = useZodForm(planSchema, {
  plan_name: '',
  monthly_fee_usd: '',
  max_users: null,
  valid_until: '',
  notes: '',
})

const entry = useZodForm(ledgerEntrySchema, {
  kind: 'payment',
  amount_usd: '',
  note: '',
  extends_until: '',
})

function hydrate(sub: Subscription): void {
  subscription.value = sub
  plan.reset({
    plan_name: sub.plan_name ?? '',
    monthly_fee_usd: sub.monthly_fee_usd ?? '',
    max_users: sub.max_users,
    valid_until: sub.valid_until ?? '',
    notes: sub.notes ?? '',
  })
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const [sub, entries] = await Promise.all([
      consoleApi.subscription(props.clientId),
      consoleApi.ledger(props.clientId),
    ])
    hydrate(sub)
    ledger.value = entries
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const status = computed(() => STATUS[subscription.value?.status ?? 'none'])
const daysLeft = computed(() => {
  const days = subscription.value?.days_left
  if (days === null || days === undefined) return null
  if (days < 0) return `Venció hace ${Math.abs(days)} ${Math.abs(days) === 1 ? 'día' : 'días'}`
  return days === 0 ? 'Vence hoy' : `Quedan ${days} ${days === 1 ? 'día' : 'días'}`
})

async function savePlan(): Promise<void> {
  await plan.handleSubmit(async (data) => {
    try {
      hydrate(await consoleApi.setSubscription(props.clientId, data))
      toast.success('Plan guardado')
    } catch (e) {
      toast.error('No se pudo guardar el plan', { description: errorMessage(e) })
    }
  })
}

async function recordEntry(): Promise<void> {
  await entry.handleSubmit(async (data) => {
    try {
      await consoleApi.recordLedgerEntry(props.clientId, data)
      toast.success(data.kind === 'payment' ? 'Pago registrado' : 'Ajuste registrado')
      entry.reset({ kind: 'payment', amount_usd: '', note: '', extends_until: '' })
      await load()
    } catch (e) {
      toast.error('No se pudo registrar el movimiento', { description: errorMessage(e) })
    }
  })
}
</script>

<template>
  <div class="billing" data-test="subscription">
    <Alert v-if="loadError" tone="danger" data-test="billing-error">
      {{ loadError }}
      <template #action>
        <Button size="sm" variant="secondary" @click="load">Reintentar</Button>
      </template>
    </Alert>

    <Card padding="md">
      <div v-if="loading" class="billing__summary">
        <Skeleton height="20px" width="40%" />
        <Skeleton height="14px" width="60%" />
      </div>
      <div v-else-if="subscription" class="billing__summary">
        <div class="billing__status" data-test="billing-status">
          <Badge :tone="status.tone" dot>{{ status.label }}</Badge>
          <span v-if="subscription.valid_until" class="billing__until">
            Hasta el {{ formatDay(subscription.valid_until) }}
          </span>
          <span v-if="daysLeft" class="billing__days">· {{ daysLeft }}</span>
        </div>
        <dl class="billing__facts">
          <div>
            <dt>Plan</dt>
            <dd>{{ subscription.plan_name ?? '—' }}</dd>
          </div>
          <div>
            <dt>Cuota mensual</dt>
            <dd>{{ subscription.monthly_fee_usd ? formatUsd(subscription.monthly_fee_usd) : '—' }}</dd>
          </div>
          <div>
            <dt>Cupo de personas</dt>
            <dd>{{ subscription.max_users ?? 'Sin límite' }}</dd>
          </div>
        </dl>
      </div>
      <p class="billing__note">
        SAVI Cloud no cobra: el pago se hace por fuera y acá se registra. La vigencia dispara el aviso
        de renovación siete días antes.
      </p>
    </Card>

    <div class="billing__forms">
      <Card title="Plan" description="Lo que se acordó con el cliente.">
        <form class="form-grid" novalidate @submit.prevent="savePlan">
          <TextField
            v-model="plan.values.plan_name"
            label="Nombre del plan"
            placeholder="Equipo, Empresa…"
            :maxlength="80"
            :error="plan.errors.value.plan_name"
            data-test="plan-name"
            @blur="plan.touch('plan_name')"
          />
          <TextField
            v-model="plan.values.monthly_fee_usd"
            label="Cuota mensual (USD)"
            inputmode="decimal"
            placeholder="120.00"
            :error="plan.errors.value.monthly_fee_usd"
            data-test="plan-fee"
            @blur="plan.touch('monthly_fee_usd')"
          />
          <TextField
            v-model="plan.values.max_users"
            label="Cupo de personas"
            type="number"
            :min="1"
            hint="Vacío: sin límite."
            :error="plan.errors.value.max_users"
            data-test="plan-users"
            @blur="plan.touch('max_users')"
          />
          <TextField
            v-model="plan.values.valid_until"
            label="Vigente hasta"
            type="date"
            :error="plan.errors.value.valid_until"
            data-test="plan-valid-until"
            @blur="plan.touch('valid_until')"
          />
          <Textarea
            v-model="plan.values.notes"
            class="form-grid__wide"
            label="Notas"
            :rows="2"
            :maxlength="500"
            :error="plan.errors.value.notes"
            data-test="plan-notes"
            @blur="plan.touch('notes')"
          />
          <div class="form-grid__wide billing__actions">
            <Button
              v-if="plan.isDirty.value"
              variant="ghost"
              :disabled="plan.submitting.value"
              @click="plan.reset()"
            >
              Descartar
            </Button>
            <Button
              type="submit"
              :loading="plan.submitting.value"
              :disabled="!plan.isDirty.value"
              data-test="plan-save"
            >
              Guardar plan
            </Button>
          </div>
        </form>
      </Card>

      <Card title="Registrar movimiento" description="Un pago recibido o un ajuste manual.">
        <form class="form-grid" novalidate @submit.prevent="recordEntry">
          <Select v-model="entry.values.kind" label="Tipo" :options="KINDS" data-test="entry-kind" />
          <TextField
            v-model="entry.values.amount_usd"
            label="Monto (USD)"
            inputmode="decimal"
            placeholder="120.00"
            :error="entry.errors.value.amount_usd"
            data-test="entry-amount"
            @blur="entry.touch('amount_usd')"
          />
          <TextField
            v-model="entry.values.note"
            class="form-grid__wide"
            label="Referencia"
            placeholder="Transferencia 4412"
            :maxlength="500"
            :error="entry.errors.value.note"
            data-test="entry-note"
            @blur="entry.touch('note')"
          />
          <TextField
            v-model="entry.values.extends_until"
            class="form-grid__wide"
            label="Extiende la vigencia hasta"
            type="date"
            hint="Opcional. Un pago puede extender la vigencia, nunca acortarla."
            :error="entry.errors.value.extends_until"
            data-test="entry-until"
            @blur="entry.touch('extends_until')"
          />
          <div class="form-grid__wide billing__actions">
            <Button type="submit" :loading="entry.submitting.value" data-test="entry-save">
              Registrar movimiento
            </Button>
          </div>
        </form>
      </Card>
    </div>

    <Card title="Movimientos" padding="none">
      <DataTable
        :columns="LEDGER_COLUMNS"
        :rows="ledger"
        row-key="id"
        :loading="loading"
        caption="Movimientos registrados"
        data-test="ledger"
      >
        <template #empty>
          <span data-test="ledger-empty">Todavía no se registró ningún movimiento.</span>
        </template>
        <template #cell-created_at="{ row }">{{ formatDateTime(row.created_at) }}</template>
        <template #cell-kind="{ row }">
          <Badge :tone="row.kind === 'payment' ? 'success' : 'info'">
            {{ row.kind === 'payment' ? 'Pago' : 'Ajuste' }}
          </Badge>
        </template>
        <template #cell-amount_usd="{ row }">
          <span class="num" data-test="ledger-row">{{ formatUsd(row.amount_usd) }}</span>
        </template>
        <template #cell-note="{ row }">
          {{ row.note }}
          <span v-if="row.extends_until" class="muted"> · cubre hasta {{ formatDay(row.extends_until) }}</span>
        </template>
      </DataTable>
    </Card>
  </div>
</template>

<style scoped>
.billing {
  display: grid;
  gap: var(--space-6);
}

.billing__summary {
  display: grid;
  gap: var(--space-5);
}

.billing__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  font-size: 13px;
}

.billing__until {
  font-weight: var(--fw-semibold);
}

.billing__days {
  color: var(--text-muted);
}

.billing__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-4);
  margin: 0;
}

.billing__facts dt {
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-subtle);
}

.billing__facts dd {
  margin: var(--space-1) 0 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: var(--fw-semibold);
}

.billing__note {
  margin: var(--space-5) 0 0;
  padding-top: var(--space-4);
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-muted);
}

.billing__forms {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
  gap: var(--space-6);
  align-items: start;
}

.billing__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
