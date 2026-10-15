<script setup lang="ts">
import { Alert, Card, DataTable, EmptyState, type TableColumn } from '@savi/ui'
import { Users } from 'lucide-vue-next'
import { watch } from 'vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { formatInt, formatUsd, relativeTime } from '@/lib/format'
import { useAsync } from '@/lib/useAsync'

const { id, client } = useClientContext()
const users = useAsync(() => consoleApi.clientUsers(id.value))
watch(id, () => users.reload())

const COLUMNS: TableColumn[] = [
  { key: 'user_ref', label: 'Persona' },
  { key: 'turns', label: 'Turnos', align: 'right', width: '110px' },
  { key: 'cost_usd', label: 'Costo', align: 'right', width: '120px' },
  { key: 'databases_used', label: 'Sucursales', align: 'right', width: '110px' },
  { key: 'last_used_at', label: 'Último uso', width: '160px' },
]
</script>

<template>
  <div class="stack">
    <Alert v-if="client?.identity_mode !== 'named'" tone="info">
      Las personas se identifican por un seudónimo: Cloud no recibe nombres ni correos.
    </Alert>
    <Card padding="none">
      <DataTable
        :columns="COLUMNS"
        :rows="users.data.value ?? []"
        row-key="user_ref"
        :loading="users.loading.value"
        caption="Personas que usaron SAVI"
      >
        <template #empty>
          <EmptyState :icon="Users" title="Sin personas activas en el período" />
        </template>
        <template #cell-user_ref="{ row }">
          <strong v-if="row.label">{{ row.label }}</strong>
          <code v-else>{{ row.user_ref.slice(0, 8) }}…</code>
        </template>
        <template #cell-turns="{ row }"><span class="num">{{ formatInt(row.turns) }}</span></template>
        <template #cell-cost_usd="{ row }">
          <span class="num">{{ formatUsd(row.cost_usd) }}</span>
        </template>
        <template #cell-last_used_at="{ row }">{{ relativeTime(row.last_used_at) }}</template>
      </DataTable>
    </Card>
  </div>
</template>
