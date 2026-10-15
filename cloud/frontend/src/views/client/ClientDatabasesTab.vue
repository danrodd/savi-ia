<script setup lang="ts">
import { Card, DataTable, EmptyState, type TableColumn } from '@savi/ui'
import { Database } from 'lucide-vue-next'
import { watch } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { formatDateTime, type Tone } from '@/lib/format'
import type { ClientDatabase } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'

const { id } = useClientContext()
const databases = useAsync(() => consoleApi.clientDatabases(id.value))
watch(id, () => databases.reload())

const COLUMNS: TableColumn[] = [
  { key: 'name', label: 'Sucursal' },
  { key: 'code', label: 'Código', width: '130px', mono: true },
  { key: 'state', label: 'Estado', width: '190px' },
  { key: 'last_connection_ok_at', label: 'Última conexión', width: '170px' },
]

function state(d: ClientDatabase): { label: string; tone: Tone } {
  if (d.credentials_unreadable) return { label: 'Credenciales ilegibles', tone: 'bad' }
  if (!d.is_active) return { label: 'Inactiva', tone: 'muted' }
  if (!d.is_usable) return { label: 'Sin conexión', tone: 'warn' }
  return { label: 'En uso', tone: 'ok' }
}
</script>

<template>
  <Card padding="none">
    <DataTable
      :columns="COLUMNS"
      :rows="databases.data.value ?? []"
      row-key="database_ref"
      :loading="databases.loading.value"
      caption="Sucursales del cliente"
    >
      <template #empty>
        <EmptyState
          :icon="Database"
          title="Todavía no informaron sucursales"
          description="Aparecen cuando una instalación vinculada envía su primer reporte."
        />
      </template>
      <template #cell-name="{ row }"><strong>{{ row.name }}</strong></template>
      <template #cell-state="{ row }">
        <StatusBadge :tone="state(row).tone" :label="state(row).label" />
      </template>
      <template #cell-last_connection_ok_at="{ row }">
        {{ formatDateTime(row.last_connection_ok_at) }}
      </template>
    </DataTable>
  </Card>
</template>
