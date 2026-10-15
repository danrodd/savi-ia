<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { consoleApi } from '@/lib/api'
import { formatDateTime, formatDay, formatUsd } from '@/lib/format'
import type { LedgerEntry, Subscription } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const props = defineProps<{ clientId: string }>()

const AMOUNT = /^-?\d{1,8}(\.\d{1,2})?$/
const DAY = /^\d{4}-\d{2}-\d{2}$/

const STATUS_LABEL: Record<Subscription['status'], string> = {
  none: 'Sin vencimiento cargado',
  active: 'Vigente',
  expiring: 'Por vencer',
  expired: 'Vencida',
}

const subscription = ref<Subscription | null>(null)
const ledger = ref<LedgerEntry[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const saved = ref(false)
const busy = ref(false)

const plan = ref({ plan_name: '', monthly_fee_usd: '', max_users: '', valid_until: '', notes: '' })
const entry = ref({
  kind: 'payment' as 'payment' | 'adjustment',
  amount_usd: '',
  note: '',
  extends_until: '',
})

function hydrate(sub: Subscription): void {
  subscription.value = sub
  plan.value = {
    plan_name: sub.plan_name ?? '',
    monthly_fee_usd: sub.monthly_fee_usd ?? '',
    max_users: sub.max_users === null ? '' : String(sub.max_users),
    valid_until: sub.valid_until ?? '',
    notes: sub.notes ?? '',
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [sub, entries] = await Promise.all([
      consoleApi.subscription(props.clientId),
      consoleApi.ledger(props.clientId),
    ])
    hydrate(sub)
    ledger.value = entries
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const statusTone = computed(() => subscription.value?.status ?? 'none')

async function savePlan(): Promise<void> {
  error.value = null
  saved.value = false
  const p = plan.value
  if (p.monthly_fee_usd.trim() && !/^\d{1,8}(\.\d{1,2})?$/.test(p.monthly_fee_usd.trim())) {
    error.value = 'La cuota va en USD, con hasta 2 decimales (por ejemplo 120 o 49.90).'
    return
  }
  if (p.max_users.trim() && !/^\d{1,6}$/.test(p.max_users.trim())) {
    error.value = 'El cupo de personas debe ser un número entero.'
    return
  }
  if (p.valid_until.trim() && !DAY.test(p.valid_until.trim())) {
    error.value = 'La vigencia es una fecha (AAAA-MM-DD).'
    return
  }
  busy.value = true
  try {
    hydrate(
      await consoleApi.setSubscription(props.clientId, {
        plan_name: p.plan_name.trim() || null,
        monthly_fee_usd: p.monthly_fee_usd.trim() || null,
        max_users: p.max_users.trim() ? Number(p.max_users) : null,
        valid_until: p.valid_until.trim() || null,
        notes: p.notes.trim() || null,
      }),
    )
    saved.value = true
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

async function record(): Promise<void> {
  error.value = null
  const e = entry.value
  if (!AMOUNT.test(e.amount_usd.trim())) {
    error.value = 'El monto va en USD, con hasta 2 decimales (por ejemplo 120 o 49.90).'
    return
  }
  if (e.kind === 'payment' && e.amount_usd.trim().startsWith('-')) {
    error.value = 'Un pago no puede ser negativo: usá un ajuste.'
    return
  }
  if (!e.note.trim()) {
    error.value = 'Anotá la referencia del movimiento (por ejemplo, número de transferencia).'
    return
  }
  if (e.extends_until.trim() && !DAY.test(e.extends_until.trim())) {
    error.value = 'La nueva vigencia es una fecha (AAAA-MM-DD).'
    return
  }
  busy.value = true
  try {
    await consoleApi.recordLedgerEntry(props.clientId, {
      kind: e.kind,
      amount_usd: e.amount_usd.trim(),
      note: e.note.trim(),
      extends_until: e.extends_until.trim() || null,
    })
    entry.value = { kind: 'payment', amount_usd: '', note: '', extends_until: '' }
    await load()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="card billing" data-test="subscription">
    <h2>Suscripción</h2>
    <p class="muted">
      SAVI Cloud no cobra: el pago se hace por fuera y acá se registra. La vigencia dispara el aviso
      de renovación.
    </p>
    <p v-if="error" class="error-text" role="alert" data-test="billing-error">{{ error }}</p>
    <p v-if="loading" class="muted">Cargando…</p>

    <template v-else-if="subscription">
      <p class="status" :data-status="statusTone" data-test="billing-status">
        {{ STATUS_LABEL[subscription.status] }}
        <span v-if="subscription.valid_until">
          · hasta {{ formatDay(subscription.valid_until) }}
          <template v-if="subscription.days_left !== null && subscription.days_left >= 0">
            ({{ subscription.days_left }} días)
          </template>
        </span>
      </p>

      <div class="grid">
        <label>
          Plan
          <input v-model="plan.plan_name" maxlength="80" data-test="plan-name" />
        </label>
        <label>
          Cuota mensual (USD)
          <input v-model="plan.monthly_fee_usd" inputmode="decimal" data-test="plan-fee" />
        </label>
        <label>
          Cupo de personas
          <input v-model="plan.max_users" inputmode="numeric" data-test="plan-users" />
        </label>
        <label>
          Vigente hasta
          <input
            v-model="plan.valid_until"
            type="date"
            data-test="plan-valid-until"
          />
        </label>
      </div>
      <label>
        Notas
        <textarea v-model="plan.notes" rows="2" maxlength="500" data-test="plan-notes" />
      </label>
      <div class="row">
        <button
          class="btn btn-primary"
          type="button"
          :disabled="busy"
          data-test="plan-save"
          @click="savePlan"
        >
          Guardar plan
        </button>
        <span v-if="saved" class="muted" role="status">Guardado.</span>
      </div>

      <fieldset>
        <legend>Registrar movimiento</legend>
        <div class="grid">
          <label>
            Tipo
            <select v-model="entry.kind" data-test="entry-kind">
              <option value="payment">Pago recibido</option>
              <option value="adjustment">Ajuste (corrección o cortesía)</option>
            </select>
          </label>
          <label>
            Monto (USD)
            <input v-model="entry.amount_usd" inputmode="decimal" data-test="entry-amount" />
          </label>
          <label>
            Referencia
            <input v-model="entry.note" maxlength="500" data-test="entry-note" />
          </label>
          <label>
            Extiende la vigencia hasta
            <input v-model="entry.extends_until" type="date" data-test="entry-until" />
          </label>
        </div>
        <div class="row">
          <button
            class="btn"
            type="button"
            :disabled="busy"
            data-test="entry-save"
            @click="record"
          >
            Registrar
          </button>
        </div>
      </fieldset>

      <table v-if="ledger.length" class="ledger" data-test="ledger">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Tipo</th>
            <th>Monto</th>
            <th>Referencia</th>
            <th>Registró</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in ledger" :key="e.id" data-test="ledger-row">
            <td>{{ formatDateTime(e.created_at) }}</td>
            <td>{{ e.kind === 'payment' ? 'Pago' : 'Ajuste' }}</td>
            <td>{{ formatUsd(e.amount_usd) }}</td>
            <td>
              {{ e.note }}
              <span v-if="e.extends_until" class="muted">
                · cubre hasta {{ formatDay(e.extends_until) }}
              </span>
            </td>
            <td>{{ e.created_by }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted" data-test="ledger-empty">Todavía no se registró ningún movimiento.</p>
    </template>
  </section>
</template>

<style scoped>
.billing {
  display: grid;
  gap: 0.9rem;
}
.grid {
  display: grid;
  gap: 0.7rem;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
}
.billing fieldset {
  display: grid;
  gap: 0.6rem;
  border: 1px solid var(--border, #d0d5dd);
  border-radius: 8px;
  padding: 0.7rem 0.9rem;
  min-width: 0;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.status {
  margin: 0;
  font-weight: 600;
}
.status[data-status='expiring'] {
  color: var(--warning, #b54708);
}
.status[data-status='expired'] {
  color: var(--danger, #b42318);
}
.ledger {
  width: 100%;
  border-collapse: collapse;
  display: block;
  overflow-x: auto;
}
.ledger th,
.ledger td {
  text-align: left;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border, #d0d5dd);
}
</style>
