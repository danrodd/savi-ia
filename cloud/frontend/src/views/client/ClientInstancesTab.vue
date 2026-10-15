<script setup lang="ts">
import { Button, Card, DataTable, EmptyState, type TableColumn } from '@savi/ui'
import { Server } from 'lucide-vue-next'
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { instanceState, relativeTime } from '@/lib/format'
import type { Instance } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const { id } = useClientContext()
const router = useRouter()
const auth = useAuthStore()
const instances = useAsync(() => consoleApi.instances({ client_id: id.value }))
watch(id, () => instances.reload())

const COLUMNS: TableColumn[] = [
  { key: 'name', label: 'Instalación' },
  { key: 'state', label: 'Estado', width: '150px' },
  { key: 'version', label: 'Versión', width: '120px', mono: true },
  { key: 'last_seen_at', label: 'Último contacto', width: '170px' },
]

function open(instance: Instance): void {
  void router.push(`/instancias/${instance.id}`)
}
</script>

<template>
  <Card padding="none">
    <DataTable
      :columns="COLUMNS"
      :rows="instances.data.value ?? []"
      row-key="id"
      :loading="instances.loading.value"
      clickable
      caption="Instalaciones del cliente"
      @row-click="open"
    >
      <template #empty>
        <EmptyState
          :icon="Server"
          title="Todavía no hay instalaciones vinculadas"
          description="Generá un token en la pestaña Vinculación y pegalo en SAVI → Administración → SAVI Cloud."
        >
          <Button
            v-if="auth.can('tokens.manage')"
            variant="secondary"
            @click="router.push(`/clientes/${id}/vinculacion`)"
          >
            Ir a Vinculación
          </Button>
        </EmptyState>
      </template>
      <template #cell-name="{ row }">
        <strong>{{ row.name }}</strong>
        <span v-if="row.outdated" class="muted"> · desactualizada</span>
      </template>
      <template #cell-state="{ row }">
        <StatusBadge :tone="instanceState(row).tone" :label="instanceState(row).label" />
      </template>
      <template #cell-version="{ row }">{{ row.version ?? '—' }}</template>
      <template #cell-last_seen_at="{ row }">{{ relativeTime(row.last_seen_at) }}</template>
    </DataTable>
  </Card>
</template>
