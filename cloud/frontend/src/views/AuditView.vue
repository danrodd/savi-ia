<script setup lang="ts">
import {
  Alert,
  Button,
  Card,
  DataTable,
  Dialog,
  EmptyState,
  PageHeader,
  type TableColumn,
  TextField,
} from '@savi/ui'
import { ScrollText, Search, X } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useQueryParam } from '@/composables/useQueryParam'
import { useTargetNames } from '@/composables/useTargetNames'
import { consoleApi } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import type { AuditEntry } from '@/lib/types'
import { errorMessage } from '@/lib/useAsync'

const entries = ref<AuditEntry[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const actor = ref('')
const action = ref('')
const viewing = ref<AuditEntry | null>(null)
// Filtro por objeto (id), en la URL: `/auditoria?target=<id>`. Se activa al pulsar un objeto.
const target = useQueryParam('target')
const { describe } = useTargetNames()

const COLUMNS: TableColumn[] = [
  { key: 'occurred_at', label: 'Cuándo', width: '170px' },
  { key: 'actor_email', label: 'Quién' },
  { key: 'action', label: 'Acción', mono: true },
  { key: 'target', label: 'Objeto' },
  { key: 'ip', label: 'IP', width: '130px', mono: true },
  { key: 'change', label: '', align: 'right', width: '120px' },
]

async function load(more = false): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const page = await consoleApi.audit({
      actor: actor.value.trim() || undefined,
      action: action.value.trim() || undefined,
      target: target.value ?? undefined,
      cursor: more ? (nextCursor.value ?? undefined) : undefined,
    })
    entries.value = more ? [...entries.value, ...page.items] : page.items
    nextCursor.value = page.next_cursor
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
void load()

// El objeto filtrado vive en la URL, que se actualiza después: se recarga cuando ya cambió.
watch(target, () => void load())

function clearFilters(): void {
  const hadTarget = target.value !== null
  actor.value = ''
  action.value = ''
  target.value = null
  if (!hadTarget) void load()
}

function filterByTarget(id: string | null): void {
  target.value = id
}

/** Descripción del objeto filtrado: sale de una fila ya cargada, si hay. */
function targetChipLabel(): string {
  const id = target.value
  const row = entries.value.find((e) => e.target_id === id)
  return describe(row?.target_type ?? null, id)?.label ?? `Objeto ${id?.slice(0, 8)}…`
}

function pretty(value: Record<string, unknown> | null): string {
  return value ? JSON.stringify(value, null, 2) : '—'
}
</script>

<template>
  <div>
    <PageHeader
      title="Auditoría"
      description="Registro de solo lectura de cada acción que modifica algo. Nunca contiene tokens ni contraseñas."
    />

    <div class="stack">
      <Card padding="md">
        <form class="filters" novalidate @submit.prevent="load()">
          <TextField v-model="actor" type="email" label="Quién" placeholder="correo@seogroup.com" />
          <TextField v-model="action" label="Acción" placeholder="instance.revoke" mono />
          <div class="filters__buttons">
            <Button type="submit" :loading="loading">
              <Search :size="14" aria-hidden="true" /> Filtrar
            </Button>
            <Button v-if="actor || action || target" variant="ghost" @click="clearFilters">
              Limpiar
            </Button>
          </div>
        </form>
        <div v-if="target" class="chip" data-test="target-chip">
          <span>Objeto: {{ targetChipLabel() }}</span>
          <button
            type="button"
            class="chip__remove"
            aria-label="Quitar filtro por objeto"
            data-test="target-chip-remove"
            @click="filterByTarget(null)"
          >
            <X :size="12" aria-hidden="true" />
          </button>
        </div>
      </Card>

      <Alert v-if="error" tone="danger">
        {{ error }}
        <template #action>
          <Button size="sm" variant="secondary" @click="load()">Reintentar</Button>
        </template>
      </Alert>

      <Card padding="none">
        <DataTable :columns="COLUMNS" :rows="entries" row-key="id" :loading="loading" caption="Registro de auditoría">
          <template #empty>
            <EmptyState :icon="ScrollText" title="No hay registros con esos filtros" />
          </template>
          <template #cell-occurred_at="{ row }">{{ formatDateTime(row.occurred_at) }}</template>
          <template #cell-actor_email="{ row }">{{ row.actor_email ?? 'Sistema' }}</template>
          <template #cell-target="{ row }">
            <div v-if="describe(row.target_type, row.target_id)" class="target">
              <button
                v-if="row.target_id"
                type="button"
                class="target__filter"
                data-test="target-filter"
                title="Ver solo los registros de este objeto"
                @click="filterByTarget(row.target_id)"
              >
                {{ describe(row.target_type, row.target_id)?.label }}
              </button>
              <span v-else>{{ describe(row.target_type, row.target_id)?.label }}</span>
              <RouterLink
                v-if="describe(row.target_type, row.target_id)?.to"
                :to="describe(row.target_type, row.target_id)?.to ?? ''"
                class="target__link"
                data-test="target-link"
              >
                Abrir
              </RouterLink>
            </div>
            <span v-else>—</span>
          </template>
          <template #cell-ip="{ row }">{{ row.ip ?? '—' }}</template>
          <template #cell-change="{ row }">
            <Button v-if="row.before || row.after" variant="ghost" size="sm" @click="viewing = row">
              Ver cambio
            </Button>
          </template>
        </DataTable>
        <template v-if="nextCursor" #footer>
          <Button variant="secondary" :loading="loading" @click="load(true)">Ver más</Button>
        </template>
      </Card>
    </div>

    <Dialog
      :open="viewing !== null"
      :title="viewing?.action ?? ''"
      :description="viewing ? `${viewing.actor_email ?? 'Sistema'} · ${formatDateTime(viewing.occurred_at)}` : ''"
      :max-width="760"
      @update:open="(open) => !open && (viewing = null)"
    >
      <div v-if="viewing" class="diff">
        <div>
          <p class="diff__title">Antes</p>
          <pre>{{ pretty(viewing.before) }}</pre>
        </div>
        <div>
          <p class="diff__title">Después</p>
          <pre>{{ pretty(viewing.after) }}</pre>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<style scoped>
.filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--space-4);
}

.filters__buttons {
  display: flex;
  gap: var(--space-2);
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-4);
  padding: 2px var(--space-2) 2px var(--space-3);
  border-radius: var(--r-pill);
  background: var(--brand-soft);
  color: var(--brand-strong);
  font-size: 12px;
  font-weight: var(--fw-medium);
}

.chip__remove {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.chip__remove:hover {
  background: var(--surface-subtle);
}

.target {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
}

.target__filter {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.target__filter:hover {
  color: var(--brand-strong);
  text-decoration: underline;
}

.target__link {
  font-size: 12px;
}

.diff {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--space-4);
}

.diff__title {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  font-weight: var(--fw-medium);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

pre {
  margin: 0;
  max-height: 50vh;
  overflow: auto;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-subtle);
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 720px) {
  .filters {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
