<script setup lang="ts">
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  DataTable,
  EmptyState,
  PageHeader,
  Select,
  type TableColumn,
} from '@savi/ui'
import { Server } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { instanceState, relativeTime } from '@/lib/format'
import type { Instance } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'

const router = useRouter()
const status = ref<string | null>(null)
const connectivity = ref<string | null>(null)
const outdated = ref(false)

const STATUS_OPTIONS = [
  { value: 'active', label: 'Activas' },
  { value: 'suspended', label: 'Suspendidas' },
  { value: 'revoked', label: 'Revocadas' },
]
const CONNECTIVITY_OPTIONS = [
  { value: 'online', label: 'En línea' },
  { value: 'offline', label: 'Sin conexión' },
]

const COLUMNS: TableColumn[] = [
  { key: 'name', label: 'Instalación' },
  { key: 'client_code', label: 'Cliente', width: '160px' },
  { key: 'state', label: 'Estado', width: '150px' },
  { key: 'version', label: 'Versión', width: '190px' },
  { key: 'last_seen_at', label: 'Último contacto', width: '160px' },
]

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.instances({
    status: status.value ?? undefined,
    connectivity: connectivity.value ?? undefined,
    outdated: outdated.value || undefined,
  }),
)
watch([status, connectivity, outdated], () => void reload())

const filtered = () => status.value !== null || connectivity.value !== null || outdated.value

function open(instance: Instance): void {
  void router.push(`/instancias/${instance.id}`)
}
</script>

<template>
  <div>
    <PageHeader
      title="Instancias"
      description="Cada instalación de SAVI vinculada a un cliente: su estado, versión y último contacto."
    />

    <div class="stack">
      <Card padding="md">
        <div class="filters">
          <Select v-model="status" label="Estado" placeholder="Todos" :options="STATUS_OPTIONS" />
          <Select
            v-model="connectivity"
            label="Conexión"
            placeholder="Con o sin conexión"
            :options="CONNECTIVITY_OPTIONS"
          />
          <Checkbox v-model="outdated" class="filters__check" label="Solo desactualizadas" />
        </div>
      </Card>

      <Alert v-if="error" tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="reload()">Reintentar</Button>
        </template>
      </Alert>

      <Card padding="none">
        <DataTable
          :columns="COLUMNS"
          :rows="data ?? []"
          row-key="id"
          :loading="loading"
          clickable
          caption="Instancias"
          @row-click="open"
        >
          <template #empty>
            <EmptyState
              :icon="Server"
              :title="filtered() ? 'No hay instancias con esos filtros' : 'Todavía no hay instancias vinculadas'"
              :description="
                filtered()
                  ? 'Probá quitando algún filtro.'
                  : 'Se vinculan desde el detalle de un cliente, en la pestaña Vinculación.'
              "
            />
          </template>
          <template #cell-name="{ row }"><strong>{{ row.name }}</strong></template>
          <template #cell-client_code="{ row }">
            <RouterLink :to="`/clientes/${row.client_id}`" @click.stop>{{ row.client_code }}</RouterLink>
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
          <template #cell-last_seen_at="{ row }">{{ relativeTime(row.last_seen_at) }}</template>
        </DataTable>
      </Card>
    </div>
  </div>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--space-4);
}

.filters__check {
  padding-bottom: var(--space-1);
}

.version {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

@media (max-width: 720px) {
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
