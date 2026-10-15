<script setup lang="ts">
import {
  Alert as AlertBox,
  Button,
  Card,
  Checkbox,
  DataTable,
  EmptyState,
  PageHeader,
  Select,
  type TableColumn,
} from '@savi/ui'
import { BellOff } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AlertResolveDialog from '@/components/AlertResolveDialog.vue'
import AlertRowActions from '@/components/AlertRowActions.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAlertActions } from '@/composables/useAlertActions'
import { useClientOptions } from '@/composables/useClientOptions'
import { useQueryParam } from '@/composables/useQueryParam'
import { alertDetail } from '@/lib/alertDetails'
import { consoleApi } from '@/lib/api'
import { ALERT_STATUS, relativeTime, SEVERITY } from '@/lib/format'
import { useRuleTitles } from '@/lib/ruleTitles'
import type { Severity } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const ruleTitle = useRuleTitles()

// Los filtros viven en la URL (`/alertas?client=…`): los enlaces desde otras pantallas funcionan.
// Arranca en las abiertas, que es lo que hay que atender; `todas` las quita.
const status = useQueryParam('status', { fallback: 'open', none: 'todas' })
const severity = useQueryParam('severity')
const clientId = useQueryParam('client')
const { options: clientOptions } = useClientOptions(() => clientId.value)

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

const auth = useAuthStore()
const canManage = computed(() => auth.can('alerts.manage'))

// En pantallas angostas las filas pasan a tarjetas (ver `cards-below`).
const CARDS_BELOW = 720

const COLUMNS = computed<TableColumn[]>(() => [
  ...(canManage.value ? [{ key: 'select', label: '', width: '44px', card: 'title' as const }] : []),
  { key: 'severity', label: 'Severidad', width: '120px' },
  { key: 'rule_code', label: 'Alerta', card: 'title' },
  { key: 'status', label: 'Estado', width: '170px' },
  { key: 'opened_at', label: 'Abierta', width: '130px' },
  { key: 'actions', label: '', align: 'right', width: '210px' },
])

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.alerts({
    status: status.value ?? undefined,
    severity: (severity.value as Severity | null) ?? undefined,
    client_id: clientId.value ?? undefined,
  }),
)
watch([status, severity, clientId], () => void reload())

const actions = useAlertActions(reload)

// Selección para las acciones masivas: solo alertas que todavía se pueden gestionar.
const rows = computed(() => data.value ?? [])
const selectable = computed(() => rows.value.filter((a) => actions.canManage(a)))
const selected = ref<Set<string>>(new Set())

// Al recargar (filtros, acciones) se descarta lo seleccionado que ya no está o ya no aplica.
watch(selectable, (list) => {
  const alive = new Set(list.map((a) => a.id))
  selected.value = new Set([...selected.value].filter((id) => alive.has(id)))
})

const allSelected = computed(
  () => selectable.value.length > 0 && selectable.value.every((a) => selected.value.has(a.id)),
)

function toggle(id: string, on: boolean): void {
  const next = new Set(selected.value)
  if (on) next.add(id)
  else next.delete(id)
  selected.value = next
}

function toggleAll(on: boolean): void {
  selected.value = on ? new Set(selectable.value.map((a) => a.id)) : new Set()
}

const selectedIds = computed(() => [...selected.value])
const selectedOpen = computed(() =>
  selectable.value.filter((a) => selected.value.has(a.id) && a.status === 'open').map((a) => a.id),
)

async function acknowledgeSelected(): Promise<void> {
  // Reconocer solo aplica a las abiertas: las ya reconocidas de la selección no se mandan.
  if (await actions.acknowledgeMany(selectedOpen.value)) selected.value = new Set()
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
          <Select
            v-model="status"
            data-test="alerts-status"
            label="Estado"
            placeholder="Todas"
            :options="STATUS_OPTIONS"
          />
          <Select
            v-model="severity"
            label="Severidad"
            placeholder="Cualquier severidad"
            :options="SEVERITY_OPTIONS"
          />
          <Select
            v-if="clientOptions.length"
            v-model="clientId"
            data-test="alerts-client"
            label="Cliente"
            placeholder="Todos los clientes"
            :options="clientOptions"
          />
        </div>
      </Card>

      <AlertBox v-if="error" tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="reload()">Reintentar</Button>
        </template>
      </AlertBox>

      <Card v-if="canManage && selectable.length" padding="md">
        <div class="bulk" data-test="alerts-bulk">
          <Checkbox
            :model-value="allSelected"
            label="Seleccionar todas las visibles"
            data-test="alerts-select-all"
            @update:model-value="toggleAll"
          />
          <span class="muted bulk__count" data-test="alerts-selected-count" aria-live="polite">
            {{
              selectedIds.length === 0
                ? 'Ninguna seleccionada'
                : selectedIds.length === 1
                  ? '1 seleccionada'
                  : `${selectedIds.length} seleccionadas`
            }}
          </span>
          <div class="bulk__actions">
            <Button
              variant="secondary"
              size="sm"
              :disabled="selectedOpen.length === 0"
              :loading="actions.bulkBusy.value"
              data-test="alerts-bulk-ack"
              @click="acknowledgeSelected"
            >
              Reconocer seleccionadas
            </Button>
            <Button
              variant="secondary"
              size="sm"
              :disabled="selectedIds.length === 0"
              data-test="alerts-bulk-resolve"
              @click="actions.openResolveMany(selectedIds)"
            >
              Resolver seleccionadas
            </Button>
          </div>
        </div>
      </Card>

      <Card padding="none">
        <DataTable
          :columns="COLUMNS"
          :rows="rows"
          row-key="id"
          :loading="loading"
          :cards-below="CARDS_BELOW"
          caption="Alertas"
        >
          <template #empty>
            <EmptyState
              :icon="BellOff"
              :title="status === 'open' ? 'No hay alertas abiertas' : 'No hay alertas con esos filtros'"
              :description="status === 'open' ? 'Todo en orden por ahora.' : undefined"
            />
          </template>
          <template #cell-select="{ row }">
            <input
              v-if="actions.canManage(row)"
              type="checkbox"
              class="pick"
              :checked="selected.has(row.id)"
              :aria-label="`Seleccionar ${ruleTitle(row.rule_code)}`"
              data-test="alert-select"
              @change="toggle(row.id, ($event.target as HTMLInputElement).checked)"
            />
          </template>
          <template #cell-severity="{ row }">
            <StatusBadge :tone="SEVERITY[row.severity].tone" :label="SEVERITY[row.severity].label" />
          </template>
          <template #cell-rule_code="{ row }">
            <div class="alert">
              <strong>{{ ruleTitle(row.rule_code) }}</strong>
              <span v-if="Object.keys(row.details).length" class="alert__detail">{{ alertDetail(row) }}</span>
              <RouterLink :to="`/clientes/${row.client_id}`" class="alert__link" data-test="alert-client">
                {{ row.client_name ?? 'Ver cliente' }}
              </RouterLink>
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
            <AlertRowActions :alert="row" :actions="actions" />
          </template>
        </DataTable>
      </Card>
    </div>

    <AlertResolveDialog :actions="actions" />
  </div>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 260px));
  gap: var(--space-4);
}

.bulk {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3) var(--space-5);
}

.bulk__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-left: auto;
}

.bulk__count {
  font-size: 12.5px;
}

.pick {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--brand);
  cursor: pointer;
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

@media (max-width: 600px) {
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }

  .bulk__actions {
    width: 100%;
    margin-left: 0;
  }
}
</style>
