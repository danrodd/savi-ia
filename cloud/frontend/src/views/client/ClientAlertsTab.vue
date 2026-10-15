<script setup lang="ts">
import { Card, DataTable, EmptyState, type TableColumn } from '@savi/ui'
import { BellOff } from 'lucide-vue-next'
import { watch } from 'vue'
import AlertResolveDialog from '@/components/AlertResolveDialog.vue'
import AlertRowActions from '@/components/AlertRowActions.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAlertActions } from '@/composables/useAlertActions'
import { alertDetail } from '@/lib/alertDetails'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { ALERT_STATUS, relativeTime, SEVERITY } from '@/lib/format'
import { useRuleTitles } from '@/lib/ruleTitles'
import { useAsync } from '@/lib/useAsync'

const { id, reloadCounts } = useClientContext()
const alerts = useAsync(() => consoleApi.alerts({ client_id: id.value }))
watch(id, () => alerts.reload())
const ruleTitle = useRuleTitles()

// Al reconocer o resolver, también se actualiza el contador de la pestaña.
const actions = useAlertActions(async () => {
  void reloadCounts()
  await alerts.reload()
})

const COLUMNS: TableColumn[] = [
  { key: 'severity', label: 'Severidad', width: '120px' },
  { key: 'rule_code', label: 'Alerta', card: 'title' },
  { key: 'status', label: 'Estado', width: '130px' },
  { key: 'opened_at', label: 'Abierta', width: '150px' },
  { key: 'actions', label: '', align: 'right', width: '210px' },
]
</script>

<template>
  <Card padding="none">
    <DataTable
      :columns="COLUMNS"
      :rows="alerts.data.value ?? []"
      row-key="id"
      :loading="alerts.loading.value"
      :cards-below="720"
      caption="Alertas del cliente"
    >
      <template #empty>
        <EmptyState :icon="BellOff" title="Sin alertas para este cliente" />
      </template>
      <template #cell-severity="{ row }">
        <StatusBadge :tone="SEVERITY[row.severity].tone" :label="SEVERITY[row.severity].label" />
      </template>
      <template #cell-rule_code="{ row }">
        <div class="alert">
          <strong>{{ ruleTitle(row.rule_code) }}</strong>
          <span v-if="Object.keys(row.details).length" class="alert__detail">{{ alertDetail(row) }}</span>
        </div>
      </template>
      <template #cell-status="{ row }">{{ ALERT_STATUS[row.status] }}</template>
      <template #cell-opened_at="{ row }">{{ relativeTime(row.opened_at) }}</template>
      <template #cell-actions="{ row }">
        <AlertRowActions :alert="row" :actions="actions" />
      </template>
    </DataTable>
  </Card>

  <AlertResolveDialog :actions="actions" />
</template>

<style scoped>
.alert {
  display: grid;
  gap: 2px;
}

.alert__detail {
  font-size: 12px;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
</style>
