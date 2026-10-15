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
  TextField,
} from '@savi/ui'
import { Server } from 'lucide-vue-next'
import { computed, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import StatusBadge from '@/components/StatusBadge.vue'
import { useClientOptions } from '@/composables/useClientOptions'
import { useQueryFlag, useQueryParam } from '@/composables/useQueryParam'
import { consoleApi } from '@/lib/api'
import { instanceState, relativeTime } from '@/lib/format'
import type { Instance } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'

const router = useRouter()

// Todos los filtros viven en la URL (`/instancias?version=1.4.2`): los enlaces desde el resumen
// y desde otras pantallas funcionan, y se pueden compartir.
const status = useQueryParam('status')
const connectivity = useQueryParam('connectivity')
const outdated = useQueryFlag('outdated')
const clientId = useQueryParam('client')
const version = useQueryParam('version')
const search = useQueryParam('q')
const { options: clientOptions } = useClientOptions(() => clientId.value)

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

// Estado, conexión y desactualizadas las filtra el backend. Cliente y versión también se
// piden al backend; la búsqueda por texto se hace acá sobre la lista ya cargada (es completa).
const { data, loading, error, reload } = useAsync(() =>
  consoleApi.instances({
    status: status.value ?? undefined,
    connectivity: connectivity.value ?? undefined,
    outdated: outdated.value || undefined,
    client_id: clientId.value ?? undefined,
    version: version.value ?? undefined,
  }),
)
watch([status, connectivity, outdated, clientId, version], () => void reload())

const rows = computed(() => {
  const all = data.value ?? []
  const needle = search.value?.trim().toLowerCase()
  if (!needle) return all
  return all.filter((i) =>
    [i.name, i.client_code, i.client_name, i.version ?? ''].some((text) =>
      text.toLowerCase().includes(needle),
    ),
  )
})

// Las versiones se arman con lo que se ha visto en la lista (el backend no tiene un catálogo);
// la que viene en la URL siempre está, aunque no haya coincidencias.
const seenVersions = new Set<string>()
const versionOptions = computed(() => {
  for (const i of data.value ?? []) if (i.version) seenVersions.add(i.version)
  if (version.value) seenVersions.add(version.value)
  return [...seenVersions].sort().map((v) => ({ value: v, label: v }))
})

const filtered = computed(
  () =>
    status.value !== null ||
    connectivity.value !== null ||
    outdated.value ||
    clientId.value !== null ||
    version.value !== null ||
    Boolean(search.value?.trim()),
)

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
          <TextField
            v-model="search"
            data-test="instances-search"
            type="search"
            label="Buscar"
            placeholder="Nombre, cliente o versión"
          />
          <Select
            v-if="clientOptions.length"
            v-model="clientId"
            data-test="instances-client"
            label="Cliente"
            placeholder="Todos los clientes"
            :options="clientOptions"
          />
          <Select
            v-model="version"
            data-test="instances-version"
            label="Versión"
            placeholder="Todas las versiones"
            :options="versionOptions"
          />
          <Select
            v-model="status"
            data-test="instances-status"
            label="Estado"
            placeholder="Todos"
            :options="STATUS_OPTIONS"
          />
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
          :rows="rows"
          row-key="id"
          :loading="loading"
          clickable
          caption="Instancias"
          @row-click="open"
        >
          <template #empty>
            <EmptyState
              :icon="Server"
              :title="filtered ? 'No hay instancias con esos filtros' : 'Todavía no hay instancias vinculadas'"
              :description="
                filtered
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
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
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
