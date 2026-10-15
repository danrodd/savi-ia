<script setup lang="ts">
import { Card, DataTable, EmptyState, type TableColumn } from '@savi/ui'
import { BellOff } from 'lucide-vue-next'
import { watch } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { ALERT_STATUS, relativeTime, SEVERITY } from '@/lib/format'
import { useRuleTitles } from '@/lib/ruleTitles'
import { useAsync } from '@/lib/useAsync'

const { id } = useClientContext()
const alerts = useAsync(() => consoleApi.alerts({ client_id: id.value }))
watch(id, () => alerts.reload())
const ruleTitle = useRuleTitles()

const COLUMNS: TableColumn[] = [
  { key: 'severity', label: 'Severidad', width: '120px' },
  { key: 'rule_code', label: 'Alerta' },
  { key: 'status', label: 'Estado', width: '130px' },
  { key: 'opened_at', label: 'Abierta', width: '150px' },
]
</script>

<template>
  <Card padding="none">
    <DataTable
      :columns="COLUMNS"
      :rows="alerts.data.value ?? []"
      row-key="id"
      :loading="alerts.loading.value"
      caption="Alertas del cliente"
    >
      <template #empty>
        <EmptyState :icon="BellOff" title="Sin alertas para este cliente" />
      </template>
      <template #cell-severity="{ row }">
        <StatusBadge :tone="SEVERITY[row.severity].tone" :label="SEVERITY[row.severity].label" />
      </template>
      <template #cell-rule_code="{ row }">{{ ruleTitle(row.rule_code) }}</template>
      <template #cell-status="{ row }">{{ ALERT_STATUS[row.status] }}</template>
      <template #cell-opened_at="{ row }">{{ relativeTime(row.opened_at) }}</template>
    </DataTable>
  </Card>
</template>
