<script setup lang="ts">
import { Badge, Card, DataTable, type TableColumn } from '@savi/ui'
import { Monitor, Server } from 'lucide-vue-next'
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import LinkingEmptyState from '@/components/LinkingEmptyState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import {
  deploymentModeLabel,
  formatInt,
  formatUsd,
  instanceState,
  relativeTime,
} from '@/lib/format'
import type { Instance } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'

const { id } = useClientContext()
const router = useRouter()
const instances = useAsync(() => consoleApi.instances({ client_id: id.value }))
watch(id, () => instances.reload())

const COLUMNS: TableColumn[] = [
  { key: 'name', label: 'Instalación', card: 'title' },
  { key: 'state', label: 'Estado', width: '150px' },
  { key: 'turns_30d', label: 'Turnos', align: 'right', width: '90px' },
  { key: 'cost_30d_usd', label: 'Costo', align: 'right', width: '110px' },
  { key: 'errors_30d', label: 'Errores', align: 'right', width: '90px' },
  { key: 'version', label: 'Versión', width: '190px' },
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
      :cards-below="720"
      caption="Instalaciones del cliente"
      @row-click="open"
    >
      <template #empty>
        <LinkingEmptyState
          :client-id="id"
          :icon="Server"
          title="Todavía no hay instalaciones vinculadas"
          description="Una instalación aparece aquí cuando se vincula con un token de este cliente. Genere el token, instale SAVI y péguelo."
        />
      </template>
      <template #cell-name="{ row }">
        <span class="name">
          <component
            :is="row.deployment_mode === 'desktop' ? Monitor : Server"
            :size="15"
            class="mode"
            role="img"
            :aria-label="deploymentModeLabel(row.deployment_mode)"
            :title="deploymentModeLabel(row.deployment_mode)"
          />
          <strong>{{ row.name }}</strong>
        </span>
      </template>
      <template #cell-turns_30d="{ row }"><span class="num">{{ formatInt(row.turns_30d ?? 0) }}</span></template>
      <template #cell-cost_30d_usd="{ row }"><span class="num">{{ formatUsd(row.cost_30d_usd ?? 0) }}</span></template>
      <template #cell-errors_30d="{ row }">
        <span class="num" :class="{ errors: (row.errors_30d ?? 0) > 0 }">{{ formatInt(row.errors_30d ?? 0) }}</span>
      </template>
      <template #cell-state="{ row }">
        <StatusBadge :tone="instanceState(row).tone" :label="instanceState(row).label" />
      </template>
      <template #cell-version="{ row }">
        <span class="version">
          <code>{{ row.version ?? '—' }}</code>
          <Badge v-if="row.outdated" tone="warning">Desactualizada</Badge>
        </span>
      </template>
      <template #cell-last_seen_at="{ row }">
        <template v-if="row.last_seen_at">{{ relativeTime(row.last_seen_at) }}</template>
        <span v-else class="muted">Vinculada {{ relativeTime(row.enrolled_at) }}</span>
      </template>
    </DataTable>
  </Card>
</template>

<style scoped>
.name,
.version {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.mode {
  flex: none;
  color: var(--text-muted);
}

.errors {
  color: var(--text-warning);
  font-weight: var(--fw-medium);
}
</style>
