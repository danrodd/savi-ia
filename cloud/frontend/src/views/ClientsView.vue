<script setup lang="ts">
import {
  Alert,
  Button,
  Card,
  DataTable,
  EmptyState,
  PageHeader,
  Select,
  type TableColumn,
  TextField,
} from '@savi/ui'
import { Building2, Plus, Search } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ClientFormDialog from '@/components/ClientFormDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import type { Client } from '@/lib/types'
import { useAsync } from '@/lib/useAsync'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
const router = useRouter()

const q = ref('')
const status = ref<string | null>(null)
const sort = ref<string | null>('code')

const STATUS_OPTIONS = [
  { value: 'active', label: 'Activos' },
  { value: 'suspended', label: 'Suspendidos' },
]
const SORT_OPTIONS = [
  { value: 'code', label: 'Código' },
  { value: 'name', label: 'Nombre' },
  { value: 'last_seen', label: 'Última actividad' },
]

const COLUMNS: TableColumn[] = [
  { key: 'code', label: 'Cliente' },
  { key: 'status', label: 'Estado', width: '130px' },
  { key: 'instances', label: 'En línea', align: 'right', width: '110px' },
  { key: 'last_seen_at', label: 'Última actividad', width: '160px' },
  { key: 'oldest_version', label: 'Versión más antigua', width: '170px', mono: true },
]

const { data, loading, error, reload } = useAsync(() =>
  consoleApi.clients({
    q: q.value.trim() || undefined,
    status: status.value ?? undefined,
    sort: sort.value ?? 'code',
  }),
)

let timer: ReturnType<typeof setTimeout> | undefined
watch([q, status, sort], () => {
  clearTimeout(timer)
  timer = setTimeout(() => void reload(), 250)
})

const creating = ref(false)

function open(client: Client): void {
  void router.push(`/clientes/${client.id}`)
}

function onCreated(client: Client): void {
  void router.push(`/clientes/${client.id}`)
}
</script>

<template>
  <div>
    <PageHeader title="Clientes" description="Empresas que usan SAVI y sus instalaciones vinculadas.">
      <template #actions>
        <Button v-if="auth.can('clients.write')" data-test="client-new" @click="creating = true">
          <Plus :size="15" aria-hidden="true" /> Nuevo cliente
        </Button>
      </template>
    </PageHeader>

    <div class="stack">
      <Card padding="md">
        <div class="filters">
          <TextField v-model="q" type="search" label="Buscar" placeholder="Código o nombre" data-test="clients-search">
            <template #prefix><Search :size="15" /></template>
          </TextField>
          <Select v-model="status" label="Estado" placeholder="Todos" :options="STATUS_OPTIONS" />
          <Select v-model="sort" label="Ordenar por" :options="SORT_OPTIONS" />
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
          :rows="data?.items ?? []"
          row-key="id"
          :loading="loading"
          clickable
          caption="Clientes"
          @row-click="open"
        >
          <template #empty>
            <EmptyState
              :icon="Building2"
              :title="q || status ? 'No hay clientes con esos filtros' : 'Todavía no hay clientes'"
              :description="q || status ? 'Probá con otra búsqueda.' : 'Creá el primero para vincular sus instalaciones.'"
            >
              <Button v-if="!q && !status && auth.can('clients.write')" @click="creating = true">
                Nuevo cliente
              </Button>
            </EmptyState>
          </template>
          <template #cell-code="{ row }">
            <div class="client">
              <strong>{{ row.name }}</strong>
              <code>{{ row.code }}</code>
            </div>
          </template>
          <template #cell-status="{ row }">
            <StatusBadge
              :tone="row.status === 'active' ? 'ok' : 'bad'"
              :label="row.status === 'active' ? 'Activo' : 'Suspendido'"
            />
          </template>
          <template #cell-instances="{ row }">
            <span class="num">{{ row.instances_online }} / {{ row.instances_total }}</span>
          </template>
          <template #cell-last_seen_at="{ row }">{{ relativeTime(row.last_seen_at) }}</template>
          <template #cell-oldest_version="{ row }">{{ row.oldest_version ?? '—' }}</template>
        </DataTable>
      </Card>
      <p v-if="data && data.total > 0" class="muted total">
        {{ data.total }} {{ data.total === 1 ? 'cliente' : 'clientes' }}
      </p>
    </div>

    <ClientFormDialog v-model:open="creating" @saved="onCreated" />
  </div>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-4);
}

.client {
  display: grid;
  gap: 2px;
}

.client code {
  font-size: 11.5px;
  color: var(--text-muted);
}

.total {
  margin: calc(-1 * var(--space-3)) 0 0;
  font-size: 12px;
}

@media (max-width: 720px) {
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
