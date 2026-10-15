<script setup lang="ts">
import {
  Alert as AlertBox,
  Button,
  Card,
  DataTable,
  Dialog,
  EmptyState,
  PageHeader,
  Select,
  type TableColumn,
  Textarea,
  toast,
} from '@savi/ui'
import { BellOff } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { ALERT_STATUS, relativeTime, SEVERITY } from '@/lib/format'
import { useRuleTitles } from '@/lib/ruleTitles'
import type { Alert, Severity } from '@/lib/types'
import { errorMessage, useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const ruleTitle = useRuleTitles()

// Arranca en las abiertas: es lo que hay que atender.
const status = ref<string | null>('open')
const severity = ref<Severity | null>(null)

const STATUS_OPTIONS = [
  { value: 'open', label: 'Abiertas' },
  { value: 'acknowledged', label: 'Reconocidas' },
  { value: 'resolved', label: 'Resueltas' },
]
const SEVERITY_OPTIONS: { value: Severity; label: string }[] = [
  { value: 'critical', label: 'Críticas' },
  { value: 'warning', label: 'Avisos' },
  { value: 'info', label: 'Info' },
]

const COLUMNS: TableColumn[] = [
  { key: 'severity', label: 'Severidad', width: '120px' },
  { key: 'rule_code', label: 'Alerta' },
  { key: 'status', label: 'Estado', width: '170px' },
  { key: 'opened_at', label: 'Abierta', width: '130px' },
  { key: 'actions', label: '', align: 'right', width: '210px' },
]

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.alerts({ status: status.value ?? undefined, severity: severity.value ?? undefined }),
)
watch([status, severity], () => void reload())

function detail(alert: Alert): string {
  return Object.entries(alert.details)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(' · ')
}

const busyId = ref<string | null>(null)

async function acknowledge(alert: Alert): Promise<void> {
  busyId.value = alert.id
  try {
    await consoleApi.acknowledgeAlert(alert.id)
    toast.success('Alerta reconocida')
    await reload()
  } catch (e) {
    toast.error('No se pudo reconocer la alerta', { description: errorMessage(e) })
  } finally {
    busyId.value = null
  }
}

const resolving = ref<Alert | null>(null)
const note = ref('')
const resolveBusy = ref(false)

function openResolve(alert: Alert): void {
  resolving.value = alert
  note.value = ''
}

async function resolve(): Promise<void> {
  const alert = resolving.value
  if (!alert) return
  resolveBusy.value = true
  try {
    await consoleApi.resolveAlert(alert.id, note.value.trim())
    toast.success('Alerta resuelta')
    resolving.value = null
    await reload()
  } catch (e) {
    toast.error('No se pudo resolver la alerta', { description: errorMessage(e) })
  } finally {
    resolveBusy.value = false
  }
}
</script>

<template>
  <div>
    <PageHeader
      title="Alertas"
      description="Problemas detectados en las instalaciones y los clientes. Reconocé una alerta cuando alguien la esté atendiendo."
    />

    <div class="stack">
      <Card padding="md">
        <div class="filters">
          <Select v-model="status" label="Estado" placeholder="Todas" :options="STATUS_OPTIONS" />
          <Select
            v-model="severity"
            label="Severidad"
            placeholder="Cualquier severidad"
            :options="SEVERITY_OPTIONS"
          />
        </div>
      </Card>

      <AlertBox v-if="error" tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="reload()">Reintentar</Button>
        </template>
      </AlertBox>

      <Card padding="none">
        <DataTable :columns="COLUMNS" :rows="data ?? []" row-key="id" :loading="loading" caption="Alertas">
          <template #empty>
            <EmptyState
              :icon="BellOff"
              :title="status === 'open' ? 'No hay alertas abiertas' : 'No hay alertas con esos filtros'"
              :description="status === 'open' ? 'Todo en orden por ahora.' : undefined"
            />
          </template>
          <template #cell-severity="{ row }">
            <StatusBadge :tone="SEVERITY[row.severity].tone" :label="SEVERITY[row.severity].label" />
          </template>
          <template #cell-rule_code="{ row }">
            <div class="alert">
              <strong>{{ ruleTitle(row.rule_code) }}</strong>
              <span v-if="Object.keys(row.details).length" class="alert__detail">{{ detail(row) }}</span>
              <RouterLink :to="`/clientes/${row.client_id}`" class="alert__link">Ver cliente</RouterLink>
            </div>
          </template>
          <template #cell-status="{ row }">
            {{ ALERT_STATUS[row.status] }}
            <span v-if="row.acknowledged_by && row.status === 'acknowledged'" class="muted alert__who">
              {{ row.acknowledged_by }}
            </span>
          </template>
          <template #cell-opened_at="{ row }">{{ relativeTime(row.opened_at) }}</template>
          <template #cell-actions="{ row }">
            <div v-if="auth.can('alerts.manage') && row.status !== 'resolved'" class="actions">
              <Button
                v-if="row.status === 'open'"
                variant="secondary"
                size="sm"
                :loading="busyId === row.id"
                @click="acknowledge(row)"
              >
                Reconocer
              </Button>
              <Button variant="secondary" size="sm" @click="openResolve(row)">Resolver</Button>
            </div>
          </template>
        </DataTable>
      </Card>
    </div>

    <Dialog
      :open="resolving !== null"
      title="Resolver alerta"
      :description="resolving ? ruleTitle(resolving.rule_code) : ''"
      :max-width="480"
      @update:open="(open) => !open && (resolving = null)"
    >
      <Textarea
        v-model="note"
        label="Nota"
        placeholder="Qué se hizo (opcional)"
        :rows="3"
        :maxlength="500"
        hint="Queda en la auditoría junto con quién la resolvió."
      />
      <template #footer>
        <Button variant="ghost" :disabled="resolveBusy" @click="resolving = null">Cancelar</Button>
        <Button :loading="resolveBusy" data-test="resolve-confirm" @click="resolve">Resolver alerta</Button>
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 260px));
  gap: var(--space-4);
}

.alert {
  display: grid;
  gap: 2px;
}

.alert__detail {
  font-size: 12px;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

.alert__link {
  font-size: 12px;
}

.alert__who {
  display: block;
  font-size: 11.5px;
}

.actions {
  display: inline-flex;
  gap: var(--space-2);
}

@media (max-width: 600px) {
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
