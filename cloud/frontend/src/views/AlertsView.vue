<script setup lang="ts">
import {
  Alert as AlertBox,
  Button,
  Card,
  DataTable,
  EmptyState,
  PageHeader,
  Select,
  type TableColumn,
} from '@savi/ui'
import { BellOff } from 'lucide-vue-next'
import { watch } from 'vue'
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

const COLUMNS: TableColumn[] = [
  { key: 'severity', label: 'Severidad', width: '120px' },
  { key: 'rule_code', label: 'Alerta' },
  { key: 'status', label: 'Estado', width: '170px' },
  { key: 'opened_at', label: 'Abierta', width: '130px' },
  { key: 'actions', label: '', align: 'right', width: '210px' },
]

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.alerts({
    status: status.value ?? undefined,
    severity: (severity.value as Severity | null) ?? undefined,
    client_id: clientId.value ?? undefined,
  }),
)
watch([status, severity, clientId], () => void reload())

const actions = useAlertActions(reload)
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
}
</style>
