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
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ClientFormDialog from '@/components/ClientFormDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { consoleApi } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import type { Client } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'
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
  { key: 'code', label: 'Cliente', card: 'title' },
  { key: 'status', label: 'Estado', width: '130px' },
  { key: 'instances', label: 'En línea', align: 'right', width: '110px' },
  { key: 'last_seen_at', label: 'Última actividad', width: '160px' },
  { key: 'oldest_version', label: 'Versión más antigua', width: '170px', mono: true },
]

// El backend pagina (`limit`/`offset`): se pide de a PAGE_SIZE y "Ver más" agrega la siguiente.
const PAGE_SIZE = 50

const items = ref<Client[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
let sequence = 0

async function load(more = false): Promise<void> {
  // La última llamada gana: un filtro nuevo descarta lo que venga de una página anterior.
  const mine = ++sequence
  loading.value = true
  error.value = null
  try {
    const page = await consoleApi.clients({
      q: q.value.trim() || undefined,
      status: status.value ?? undefined,
      sort: sort.value ?? 'code',
      limit: PAGE_SIZE,
      offset: more ? items.value.length : 0,
    })
    if (mine !== sequence) return
    if (more) {
      const known = new Set(items.value.map((c) => c.id))
      items.value = [...items.value, ...page.items.filter((c) => !known.has(c.id))]
    } else {
      items.value = page.items
    }
    total.value = page.total
  } catch (e) {
    if (mine === sequence) error.value = errorMessage(e)
  } finally {
    if (mine === sequence) loading.value = false
  }
}
void load()

const hasMore = computed(() => items.value.length < total.value)

let timer: ReturnType<typeof setTimeout> | undefined
watch([q, status, sort], () => {
  clearTimeout(timer)
  timer = setTimeout(() => void load(), 250)
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
          <Button size="sm" variant="secondary" @click="load()">Reintentar</Button>
        </template>
      </Alert>

      <Card padding="none">
        <DataTable
          :columns="COLUMNS"
          :rows="items"
          row-key="id"
          :loading="loading"
          clickable
          :cards-below="720"
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
        <template v-if="hasMore" #footer>
          <Button variant="secondary" :loading="loading" data-test="clients-more" @click="load(true)">
            Ver más
          </Button>
        </template>
      </Card>
      <p v-if="total > 0" class="muted total" data-test="clients-total">
        <template v-if="hasMore">Mostrando {{ items.length }} de {{ total }} clientes</template>
        <template v-else>{{ total }} {{ total === 1 ? 'cliente' : 'clientes' }}</template>
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
